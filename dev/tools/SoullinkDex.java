import com.dabomstew.pkrandom.pokemon.Evolution;
import com.dabomstew.pkrandom.pokemon.EvolutionType;
import com.dabomstew.pkrandom.pokemon.Move;
import com.dabomstew.pkrandom.pokemon.MoveLearnt;
import com.dabomstew.pkrandom.pokemon.Pokemon;
import com.dabomstew.pkrandom.pokemon.Trainer;
import com.dabomstew.pkrandom.pokemon.TrainerPokemon;
import com.dabomstew.pkrandom.romhandlers.AbstractDSRomHandler;
import com.dabomstew.pkrandom.romhandlers.Gen3RomHandler;
import com.dabomstew.pkrandom.romhandlers.Gen4RomHandler;
import com.dabomstew.pkrandom.romhandlers.Gen5RomHandler;
import com.dabomstew.pkrandom.romhandlers.RomHandler;

import java.io.OutputStream;
import java.io.PrintStream;
import java.io.Writer;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.EnumSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.TreeMap;

/**
 * Reads a (randomized) GBA/NDS ROM with the Universal Pokemon Randomizer ZX and writes Pokedex data as JSON.
 * Usage: java -cp PokeRandoZX.jar;soullink-dex.jar SoullinkDex <rom> <target.json>
 */
public class SoullinkDex {

    /** Format version of the output; 2 adds gym leaders, Elite Four and champion ("trainer"). */
    static final int FORMAT = 2;


    /** Evolution kinds whose extraInfo is an item number. */
    static final Set<EvolutionType> WITH_ITEM = EnumSet.of(EvolutionType.STONE, EvolutionType.STONE_MALE_ONLY,
            EvolutionType.STONE_FEMALE_ONLY, EvolutionType.TRADE_ITEM, EvolutionType.LEVEL_ITEM_DAY,
            EvolutionType.LEVEL_ITEM_NIGHT, EvolutionType.STONE_ULTRA);

    /** Command line entry point: reads the ROM and writes the JSON file. */
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: SoullinkDex <rom> <target.json>");
            System.exit(2);
        }
        try {
            write(Paths.get(args[0]), Paths.get(args[1]));
        } catch (Exception error) {
            System.err.println("ERROR: " + error);
            error.printStackTrace();
            System.exit(1);
        }
    }

    /** Reads the ROM with the matching ZX handler and writes the Pokedex JSON atomically. */
    static void write(Path rom, Path target) throws Exception {
        PrintStream silent = new PrintStream(OutputStream.nullOutputStream());
        RomHandler.Factory[] factories = {new Gen3RomHandler.Factory(), new Gen4RomHandler.Factory(),
                new Gen5RomHandler.Factory()};
        RomHandler handler = null;
        for (RomHandler.Factory factory : factories) {
            if (factory.isLoadable(rom.toString())) {
                handler = factory.create(new Random(), silent);
                break;
            }
        }
        if (handler == null) {
            throw new IllegalArgumentException("ROM not supported: " + rom);
        }


        Path link = handler instanceof AbstractDSRomHandler ? uniqueLink(rom, target) : null;
        try {
            if (!handler.loadRom((link != null ? link : rom).toString())) {
                throw new IllegalStateException("ROM not loadable: " + rom);
            }
            String json = json(handler);
            Files.createDirectories(target.toAbsolutePath().getParent());
            Path tmp = target.resolveSibling(target.getFileName() + ".tmp");
            try (Writer out = Files.newBufferedWriter(tmp, StandardCharsets.UTF_8)) {
                out.write(json);
            }
            Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } finally {
            if (handler instanceof AbstractDSRomHandler) {
                ((AbstractDSRomHandler) handler).closeInnerRom();
            }
            if (link != null) {
                Files.deleteIfExists(link);
            }
        }
    }

    /** Hard link with a unique name beside the target file; null if the file system allows none. */
    static Path uniqueLink(Path rom, Path target) {
        Path dir = target.toAbsolutePath().getParent();
        Path link = dir.resolve("dex" + ProcessHandle.current().pid() + "_" + System.nanoTime() % 100000 + ".nds");
        try {
            Files.createDirectories(dir);
            return Files.createLink(link, rom.toAbsolutePath());
        } catch (Exception error) {
            return null;
        }
    }

    /** Builds the JSON text with Pokemon, moves, items, locations and trainers. */
    static String json(RomHandler handler) throws Exception {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"format\": ").append(FORMAT)
          .append(", \"rom_code\": ").append(text(handler.getROMCode()))
          .append(", \"generation\": ").append(handler.generationOfPokemon());

        String[] itemNames = handler.getItemNames();
        Map<Integer, String> items = new TreeMap<>();
        Map<Integer, List<MoveLearnt>> learnsets = handler.getMovesLearnt();
        sb.append(",\n\"pokemon\": [");
        boolean first = true;
        for (Pokemon p : handler.getPokemon()) {
            if (p == null) {
                continue;
            }
            sb.append(first ? "\n" : ",\n");
            first = false;
            sb.append("{\"nr\": ").append(p.number)
              .append(", \"name\": ").append(text(name(p.name)))
              .append(", \"types\": [").append(text(p.primaryType == null ? null : p.primaryType.name()));
            if (p.secondaryType != null && p.secondaryType != p.primaryType) {
                sb.append(", ").append(text(p.secondaryType.name()));
            }
            sb.append("], \"values\": [").append(p.hp).append(", ").append(p.attack).append(", ").append(p.defense)
              .append(", ").append(p.spatk).append(", ").append(p.spdef).append(", ").append(p.speed).append("]");
            sb.append(", \"evolutions\": [");
            boolean firstEvolution = true;
            for (Evolution ev : p.evolutionsFrom) {
                Pokemon target = ev.to.baseForme != null ? ev.to.baseForme : ev.to;
                sb.append(firstEvolution ? "" : ", ").append("{\"target\": ").append(target.number)
                  .append(", \"kind\": ").append(text(ev.type.name()))
                  .append(", \"value\": ").append(ev.extraInfo).append("}");
                firstEvolution = false;
                if (WITH_ITEM.contains(ev.type) && ev.extraInfo > 0 && ev.extraInfo < itemNames.length) {
                    items.put(ev.extraInfo, name(itemNames[ev.extraInfo]));
                }
            }
            sb.append("], \"learnset\": [");
            List<MoveLearnt> learnset = learnsets.get(p.number);
            if (learnset != null) {
                for (int i = 0; i < learnset.size(); i++) {
                    MoveLearnt ml = learnset.get(i);
                    sb.append(i == 0 ? "" : ", ").append("[").append(ml.level).append(", ").append(ml.move).append("]");
                }
            }
            sb.append("]}");
        }
        sb.append("],\n\"moves\": [");
        first = true;
        for (Move m : handler.getMoves()) {
            if (m == null) {
                continue;
            }
            sb.append(first ? "\n" : ",\n");
            first = false;
            sb.append("{\"nr\": ").append(m.number)
              .append(", \"name\": ").append(text(name(m.name)))
              .append(", \"type\": ").append(text(m.type == null ? null : m.type.name()))
              .append(", \"strength\": ").append(m.power)
              .append(", \"accuracy\": ").append(Math.round(m.hitratio))
              .append(", \"ap\": ").append(m.pp)
              .append(", \"category\": ").append(text(m.category == null ? null : m.category.name())).append("}");
        }
        sb.append("],\n\"items\": ").append(object(items));
        sb.append(",\n\"locations\": ").append(object(locations(handler)));
        sb.append(",\n\"trainer\": ").append(trainer(handler)).append("}\n");
        return sb.toString();
    }

    /** Gym leaders, Elite Four and champion (randomizer tags) with team and highest level. */
    static String trainer(RomHandler handler) {
        StringBuilder sb = new StringBuilder("[");
        boolean first = true;
        for (Trainer tr : handler.getTrainers()) {
            if (tr == null || tr.tag == null
                    || !tr.tag.matches("GYM\\d+-LEADER|ELITE\\d+(-\\d+)?|CHAMPION|RIVAL\\d+(-\\d+)?")) {
                continue;
            }
            int highest = 0;
            StringBuilder team = new StringBuilder("[");
            for (TrainerPokemon tp : tr.pokemon) {
                highest = Math.max(highest, tp.level);
                team.append(team.length() > 1 ? ", " : "").append("[")
                    .append(tp.pokemon == null ? 0 : tp.pokemon.number).append(", ").append(tp.level).append("]");
            }
            String name = tr.name;
            if ((name == null || name.isBlank()) && tr.fullDisplayName != null) {
                name = tr.fullDisplayName.substring(tr.fullDisplayName.trim().lastIndexOf(' ') + 1);
            }
            sb.append(first ? "\n" : ",\n").append("{\"tag\": ").append(text(tr.tag))
              .append(", \"index\": ").append(tr.index)
              .append(", \"name\": ").append(text(name == null ? null : name(name.trim())))
              .append(", \"max_level\": ").append(highest)
              .append(", \"team\": ").append(team).append("]}");
            first = false;
        }
        return sb.append("]").toString();
    }

    /** Catch location id as in the save mapped to its name. */
    static Map<Integer, String> locations(RomHandler handler) throws Exception {
        Map<Integer, String> locations = new TreeMap<>();
        if (handler instanceof Gen3RomHandler) {
            locationsGen3(handler, locations);
        } else {
            Object entry = field(handler, "romEntry");
            int text = (Integer) method(entry, "getInt", String.class).invoke(entry, "MapNamesTextOffset");
            @SuppressWarnings("unchecked")
            List<String> names = handler instanceof Gen4RomHandler
                    ? (List<String>) method(handler, "getStrings", int.class).invoke(handler, text)
                    : (List<String>) method(handler, "getStrings", boolean.class, int.class).invoke(handler, false, text);
            for (int id = 0; id < names.size(); id++) {
                String name = locationName(names.get(id), false);
                if (!name.isEmpty()) {
                    locations.put(id, name);
                }
            }
        }
        return locations;
    }



    /** Generation 3: catch location is the map section (MAPSEC); RSE has 8-byte entries (x, y, w, h, name pointer), FRLG a pointer table from MAPSEC 0x58 (Kanto). */
    static void locationsGen3(RomHandler handler, Map<Integer, String> locations) throws Exception {
        Object entry = field(handler, "romEntry");
        int table = (Integer) method(entry, "getValue", String.class).invoke(entry, "MapLabels");
        int romType = (Integer) field(entry, "romType");
        byte[] rom = (byte[]) field(handler, "rom");
        if (table <= 0) {
            return;
        }
        Method pointer = method(handler, "readPointer", int.class);
        Method readString = method(handler, "readVariableLengthString", int.class);
        boolean frlg = romType == 3;
        int from = frlg ? 0x58 : 0;
        int to = frlg ? 0xC5 : romType == 2 ? 0xD5 : 0x58;
        for (int id = from; id < to; id++) {
            int position = frlg ? table + (id - 0x58) * 4 : table + id * 8 + 4;
            if (position + 4 > rom.length) {
                break;
            }
            int target = (Integer) pointer.invoke(handler, position);
            if (target <= 0 || target >= rom.length) {
                continue;
            }
            String name = locationName((String) readString.invoke(handler, target), true);
            if (!name.isEmpty()) {
                locations.put(id, name);
            }
        }
    }

    /** Cleans up a location name from the game text: control codes, line breaks, placeholder entries and capitalization. */
    static String locationName(String raw, boolean gen3) {
        if (raw == null) {
            return "";
        }
        String name = raw.replaceAll("\\\\v[0-9A-Fa-f]{2}", "TEAM").replaceAll("\\\\[a-z]", " ").replace("\n", " ")
                .replaceAll("\\s+", " ").trim();
        if (name.chars().anyMatch(c -> c >= 0xE000 && c <= 0xF8FF) || name.chars().noneMatch(Character::isLetter)) {
            return "";
        }
        return gen3 ? titleCase(name) : name;
    }

    static final Set<String> SMALL_WORDS = Set.of("im", "am", "an", "in", "zu", "of");

    /**
     * Generation 3 (and Pokemon in DP/Pt) are all caps in the ROM: BULBASAUR becomes Bulbasaur, HO-OH Ho-Oh, ROCKET HQ keeps HQ.
     * Names that are already mixed case stay unchanged.
     */
    /** Display name of a Pokemon, move or item: all-caps text is converted to title case. */
    static String name(String raw) {
        if (raw == null || raw.chars().anyMatch(c -> Character.isLowerCase(c) && c != 'é')) {
            return raw;
        }
        return titleCase(raw);
    }

    /** Converts an all-caps name to title case, keeping short small words lower case. */
    static String titleCase(String raw) {
        StringBuilder sb = new StringBuilder(raw.length());
        for (String word : raw.split(" ", -1)) {
            if (sb.length() > 0) {
                sb.append(' ');
            }
            if (word.length() <= 2 && word.chars().allMatch(Character::isLetter)) {
                String lowerWord = word.toLowerCase(Locale.ROOT);
                sb.append(sb.length() > 0 && SMALL_WORDS.contains(lowerWord) ? lowerWord : word);
                continue;
            }
            boolean wordStart = true;
            for (int i = 0; i < word.length(); i++) {
                char c = word.charAt(i);
                if (Character.isLetter(c)) {
                    sb.append(wordStart ? c : Character.toLowerCase(c));
                    wordStart = false;
                } else {
                    sb.append(c);
                    wordStart = !Character.isDigit(c) && c != '\'' && c != '’';
                }
            }
        }
        return sb.toString();
    }

    /** Reads a (possibly private) field of an object or its superclasses by reflection. */
    static Object field(Object object, String name) throws Exception {
        for (Class<?> k = object.getClass(); k != null; k = k.getSuperclass()) {
            try {
                Field f = k.getDeclaredField(name);
                f.setAccessible(true);
                return f.get(object);
            } catch (NoSuchFieldException next) {

            }
        }
        throw new NoSuchFieldException(name);
    }

    /** Finds a (possibly private) method of an object or its superclasses by reflection. */
    static Method method(Object object, String name, Class<?>... params) throws Exception {
        for (Class<?> k = object.getClass(); k != null; k = k.getSuperclass()) {
            try {
                Method m = k.getDeclaredMethod(name, params);
                m.setAccessible(true);
                return m;
            } catch (NoSuchMethodException next) {

            }
        }
        throw new NoSuchMethodException(name);
    }

    /** Renders a map as a JSON object with number keys. */
    static String object(Map<Integer, String> values) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<Integer, String> e : values.entrySet()) {
            sb.append(first ? "" : ", ").append('"').append(e.getKey()).append("\": ").append(text(e.getValue()));
            first = false;
        }
        return sb.append("}").toString();
    }

    /** Renders a string as a JSON string literal; null becomes null. */
    static String text(String s) {
        if (s == null) {
            return "null";
        }
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.append('"').toString();
    }
}

/* Pokemon-Soullink: link cable between several mGBA libretro cores in one process.
 *
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */
#ifndef SOULLINK_LINK_H
#define SOULLINK_LINK_H

#include <stdbool.h>

struct mCore;

/* Replaces core->runFrame: runs one frame in lockstep. false = not connected (continue normally). */
bool soullinkLinkFrame(struct mCore* core);
/* Before unloading the game: pull the cable. */
void soullinkLinkUnload(struct mCore* core);

#endif

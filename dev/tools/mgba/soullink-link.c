/* Pokemon-Soullink: link cable between several mGBA libretro cores in one process.
 *
 * Every player loads an own copy of this DLL (own global state) and runs in an own thread. The cores are connected
 * through mGBA's lockstep coordinator (like "new multiplayer window" in mGBA): one copy creates it with
 * soullink_link_new() and all players attach with soullink_link_connect(). While a player sleeps (waits for the
 * others), retro_run waits here - at most ~50 ms, so a paused partner never holds anybody forever.
 *
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */
#include "soullink-link.h"
#include "libretro.h"

#include <mgba/core/core.h>
#include <mgba/core/lockstep.h>
#include <mgba/internal/gba/sio/lockstep.h>
#include <mgba-util/threading.h>

#include <stdlib.h>
#include <string.h>

#define WAIT_MS 5
#define WAIT_ROUNDS 10

struct mCore* soullinkCore(void);

struct SoullinkUser {
	struct mLockstepUser d;
	Mutex mutex;
	Condition wakeup;
	bool asleep;
	int wishId;
	int playerId;
};

static struct GBASIOLockstepDriver _driver;
static struct SoullinkUser _user;
static bool _userReady = false;
static bool _connected = false;

/* Called by the coordinator in its own thread (with its mutex): only remember, waiting happens in soullinkLinkFrame. */
static void _userSleep(struct mLockstepUser* user) {
	struct SoullinkUser* self = (struct SoullinkUser*) user;
	MutexLock(&self->mutex);
	self->asleep = true;
	MutexUnlock(&self->mutex);
}

/* Called by another player's thread. */
static void _userWake(struct mLockstepUser* user) {
	struct SoullinkUser* self = (struct SoullinkUser*) user;
	MutexLock(&self->mutex);
	self->asleep = false;
	ConditionWake(&self->wakeup);
	MutexUnlock(&self->mutex);
}

static int _wishId(struct mLockstepUser* user) {
	return ((struct SoullinkUser*) user)->wishId;
}

static void _idChanged(struct mLockstepUser* user, int id) {
	((struct SoullinkUser*) user)->playerId = id;
}

/* true = awake; false = the partner did not answer in time (abort the frame, continue with the next one). */
static bool _waitUntilAwake(void) {
	int rounds = 0;
	MutexLock(&_user.mutex);
	while (_user.asleep && rounds < WAIT_ROUNDS) {
		ConditionWaitTimed(&_user.wakeup, &_user.mutex, WAIT_MS);
		++rounds;
	}
	bool awake = !_user.asleep;
	MutexUnlock(&_user.mutex);
	return awake;
}

bool soullinkLinkFrame(struct mCore* core) {
	if (!_connected) {
		return false;
	}
	uint32_t frame = core->frameCounter(core);
	while (frame == core->frameCounter(core)) {
		if (!_waitUntilAwake()) {
			break;
		}
		core->runLoop(core);
	}
	return true;
}

RETRO_API void soullink_link_disconnect(void);

void soullinkLinkUnload(struct mCore* core) {
	UNUSED(core);
	soullink_link_disconnect();
}

/* Creates the coordinator (once per group, with any copy of the DLL). */
RETRO_API void* soullink_link_new(void) {
	struct GBASIOLockstepCoordinator* coordinator = calloc(1, sizeof(*coordinator));
	if (coordinator) {
		GBASIOLockstepCoordinatorInit(coordinator);
	}
	return coordinator;
}

/* Free only when no player is connected anymore. */
RETRO_API void soullink_link_free(void* coordinator) {
	if (!coordinator) {
		return;
	}
	GBASIOLockstepCoordinatorDeinit(coordinator);
	free(coordinator);
}

/* Call in the thread of this core between two retro_run calls. wishId: 0 = player 1 (leader), 1-3 the others. */
RETRO_API bool soullink_link_connect(void* coordinator, int wishId) {
	struct mCore* core = soullinkCore();
	if (_connected || !coordinator || !core || core->platform(core) != mPLATFORM_GBA) {
		return false;
	}
	if (!_userReady) {
		memset(&_user, 0, sizeof(_user));
		MutexInit(&_user.mutex);
		ConditionInit(&_user.wakeup);
		_userReady = true;
	}
	_user.d.sleep = _userSleep;
	_user.d.wake = _userWake;
	_user.d.requestedId = _wishId;
	_user.d.playerIdChanged = _idChanged;
	_user.asleep = false;
	_user.wishId = wishId;
	_user.playerId = -1;
	GBASIOLockstepDriverCreate(&_driver, &_user.d);
	GBASIOLockstepCoordinatorAttach(coordinator, &_driver);
	core->setPeripheral(core, mPERIPH_GBA_LINK_PORT, &_driver.d);
	_connected = true;
	return true;
}

/* Pulls the cable; also in the thread of this core. */
RETRO_API void soullink_link_disconnect(void) {
	if (!_connected) {
		return;
	}
	struct mCore* core = soullinkCore();
	struct GBASIOLockstepCoordinator* coordinator = _driver.coordinator;
	if (core) {
		core->setPeripheral(core, mPERIPH_GBA_LINK_PORT, NULL);
	}
	if (coordinator) {
		GBASIOLockstepCoordinatorDetach(coordinator, &_driver);
	}
	_connected = false;
	_userWake(&_user.d);
}

/* Own player number on the cable (0 = leader) or -1. */
RETRO_API int soullink_link_player(void) {
	return _connected ? _user.playerId : -1;
}

/* How many cores are attached to the coordinator right now. */
RETRO_API int soullink_link_count(void* coordinator) {
	return coordinator ? (int) GBASIOLockstepCoordinatorAttached(coordinator) : 0;
}

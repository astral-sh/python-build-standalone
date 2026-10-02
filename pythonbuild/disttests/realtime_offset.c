/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

#define _GNU_SOURCE

#include <dlfcn.h>
#include <stdlib.h>
#include <time.h>

typedef int (*clock_gettime_fn)(clockid_t, struct timespec *);

int
clock_gettime(clockid_t clock_id, struct timespec *value)
{
    static clock_gettime_fn real_clock_gettime;

    if (real_clock_gettime == NULL) {
        real_clock_gettime = (clock_gettime_fn)dlsym(RTLD_NEXT, "clock_gettime");
        if (real_clock_gettime == NULL) {
            abort();
        }
    }

    int result = real_clock_gettime(clock_id, value);
    if (result == 0 && clock_id == CLOCK_REALTIME) {
        const char *offset = getenv("REALTIME_OFFSET_SECONDS");
        if (offset != NULL) {
            value->tv_sec += strtol(offset, NULL, 10);
        }
    }

    return result;
}

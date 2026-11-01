#include "host_critical_section.h"

#include <pthread.h>
#include <stdlib.h>

static pthread_mutex_t critical_section = PTHREAD_MUTEX_INITIALIZER;

void host_enter_critical_section(void)
{
    if (pthread_mutex_lock(&critical_section) != 0) {
        abort();
    }
}

void host_exit_critical_section(void)
{
    if (pthread_mutex_unlock(&critical_section) != 0) {
        abort();
    }
}

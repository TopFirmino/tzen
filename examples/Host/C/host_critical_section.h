#ifndef HOST_CRITICAL_SECTION_H
#define HOST_CRITICAL_SECTION_H

void host_enter_critical_section(void);
void host_exit_critical_section(void);

#define TZEN_TH_ENTER_CRITICAL_SECTION_RX_QUEUE() host_enter_critical_section()
#define TZEN_TH_EXIT_CRITICAL_SECTION_RX_QUEUE() host_exit_critical_section()

#endif

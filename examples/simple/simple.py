"""This module implements testcases regarding Firware Updates."""

from tzen import tz_testcase, tz_fixture, tz_step
import time


@tz_fixture
class FimwareConnectionFixture():
    """This fixture is used to load and remove a firmware executable."""
    
    def __init__(self, executable_name="firmware_v1.1.bin", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executable_name = executable_name
        
    def setup(self):
        load_executable(self.executable_name)
        
    def teardown(self):
        remove_executable(self.executable_name)
        
        

@tz_testcase
class TC_0002():
    """ @name: TC_0002
        @description: This test case verifies a successful Over-The-Air (OTA) firmware update.
        @Requirements: [HLR_0010, HLR_0011, HLR_0012]
        @Inputs: {'Firmware Image': 'firmware_v1.1.bin (with valid CRC)',
                  'Device State': 'Idle, connected to update server'}
        @Outputs: { 'Serial Log': '[OTA] Update complete. Rebooting., followed by [BOOT] System OK. Version: 1.1',
                    'Device': 'Reboots and runs the new firmware.'}
        @ExpectedResult: The device successfully updates its firmware, reboots, and runs the new version.
        """
        
    def __init__(self):
        pass
    
    @tz_step
    def step1(self):
        """Power on the device with firmware_v1.0.bin."""        
        assert self.is_device_on(), "Device should be powered on."
        
    @tz_step
    def step2(self):
        """Initiate an OTA update from the server with firmware_v1.1.bin."""
        self.start_ota_update()
        self.logger.info("Starting OTA update with firmware_v1.1.bin")
        assert self.is_ota_update_in_progress(), "OTA update should be in progress."
    
    @tz_step
    def step3(self):
        """Wait for the update process to complete."""
        while not self.is_ota_update_complete():
            self.logger.info("Waiting for OTA update to complete...")
            time.sleep(3)
        
        assert self.is_ota_update_complete(), "OTA update should be complete."
        
    @tz_step
    def step4(self):
        """Monitor the serial log for reboot and version confirmation."""
        assert self.check_serial_log_for("[OTA] Update complete. Rebooting.")
        
        
@tz_testcase
class TC_0003():
    """ @name: TC_0003
        @description: This test case verifies a successful Over-The-Air (OTA) firmware update.
        @Requirements: [HLR_0010, HLR_0011, HLR_0012]
        @Inputs: {'Firmware Image': 'firmware_v1.1.bin (with valid CRC)',
                  'Device State': 'Idle, connected to update server'}
        @Outputs: { 'Serial Log': '[OTA] Update complete. Rebooting., followed by [BOOT] System OK. Version: 1.1',
                    'Device': 'Reboots and runs the new firmware.'}
        @ExpectedResult: The device successfully updates its firmware, reboots, and runs the new version.
        """
        
    def __init__(self):
        pass
    
    @tz_step
    def step1(self):
        """Power on the device with firmware_v1.0.bin."""        
        assert self.is_device_on(), "Device should be powered on."
        
    @tz_step
    def step2(self):
        """Initiate an OTA update from the server with firmware_v1.1.bin."""
        self.start_ota_update()
        self.logger.info("Starting OTA update with firmware_v1.1.bin")
        assert self.is_ota_update_in_progress(), "OTA update should be in progress."
    
    @tz_step
    def step3(self):
        """Wait for the update process to complete."""
        while not self.is_ota_update_complete():
            self.logger.info("Waiting for OTA update to complete...")
            time.sleep(3)
        
        assert self.is_ota_update_complete(), "OTA update should be complete."
        
    @tz_step
    def step4(self):
        """Monitor the serial log for reboot and version confirmation."""
        assert self.check_serial_log_for("[OTA] Update complete. Rebooting.")
        
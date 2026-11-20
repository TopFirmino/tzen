--  Tzen
--  Author: L. Furcas
--  SPDX-License-Identifier: MPL-2.0

with Interfaces.C;
with System;
with Tzen_Bindings;

package Host_Pipe is
   function Init return Tzen_Bindings.C_Bool
     with Import, Convention => C, External_Name => "host_io_init";
   function Read_Byte (Value : access Tzen_Bindings.Byte) return Interfaces.C.int
     with Import, Convention => C, External_Name => "host_read_byte";
   function Send_Bytes
     (Frame : System.Address; Length : Tzen_Bindings.Size_T;
      User_Data : System.Address) return Tzen_Bindings.C_Bool
     with Import, Convention => C, External_Name => "host_send_bytes";
end Host_Pipe;

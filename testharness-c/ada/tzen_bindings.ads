--  Tzen
--  Author: L. Furcas
--  SPDX-License-Identifier: MPL-2.0

with Interfaces;
with Interfaces.C;
with Interfaces.C.Strings;
with System;

package Tzen_Bindings is
   subtype Byte is Interfaces.Unsigned_8;
   subtype UInt32 is Interfaces.Unsigned_32;
   subtype Size_T is Interfaces.C.size_t;
   subtype C_Bool is Interfaces.C.C_bool;
   subtype Chars_Ptr is Interfaces.C.Strings.chars_ptr;

   type Log_Level is (Info, Warning, Error)
     with Convention => C, Size => Interfaces.C.int'Size;
   for Log_Level use (Info => 0, Warning => 1, Error => 2);

   type Test_Status is (Success, Fail, Aborted)
     with Convention => C, Size => Interfaces.C.int'Size;
   for Test_Status use (Success => 0, Fail => 1, Aborted => 2);

   type Step_Result is (Pass_Next, Wait_Sync, Yield, Step_Fail, Done_Pass)
     with Convention => C, Size => Interfaces.C.int'Size;
   for Step_Result use
     (Pass_Next => 0, Wait_Sync => 1, Yield => 2, Step_Fail => 3,
      Done_Pass => 4);

   type Engine_State is (Idle, Running_Step, Waiting_Sync)
     with Convention => C, Size => Interfaces.C.int'Size;
   for Engine_State use (Idle => 0, Running_Step => 1, Waiting_Sync => 2);

   Source_Test : constant UInt32 := 0;

   type Execution_Ref is record
      Run_Id     : UInt32;
      Test_Index : UInt32;
   end record with Convention => C;

   type Context is limited private;
   type Context_Access is access all Context with Convention => C;

   type Step_Callback is access function (Ctx : Context_Access) return Step_Result
     with Convention => C;
   type Setup_Callback is access function (Ctx : Context_Access) return C_Bool
     with Convention => C;
   type Teardown_Callback is access procedure
     (Ctx : Context_Access; Status : Test_Status) with Convention => C;
   type Send_Callback is access function
     (Frame : System.Address; Length : Size_T; User_Data : System.Address)
      return C_Bool with Convention => C;
   type Clock_Callback is access function
     (User_Data : System.Address) return UInt32 with Convention => C;

   type Step_Array is array (Natural range <>) of aliased Step_Callback
     with Convention => C;
   type Step_Array_Pointer is access constant Step_Callback with Convention => C;

   type Test_Descriptor is record
      Name        : Chars_Ptr := Interfaces.C.Strings.Null_Ptr;
      Steps       : Step_Array_Pointer := null;
      Num_Steps   : UInt32 := 0;
      On_Setup    : Setup_Callback := null;
      On_Teardown : Teardown_Callback := null;
   end record with Convention => C;

   type Test_Array is array (Natural range <>) of aliased Test_Descriptor
     with Convention => C;
   type Test_Array_Pointer is access constant Test_Descriptor with Convention => C;

   type Configuration is record
      Send_Bytes : Send_Callback := null;
      Get_Us     : Clock_Callback := null;
      User_Data  : System.Address := System.Null_Address;
      Tests      : Test_Array_Pointer := null;
      Num_Tests  : Size_T := 0;
   end record with Convention => C;

   function Init (Config : not null access constant Configuration) return C_Bool
     with Import, Convention => C, External_Name => "tzen_th_init";
   procedure Feed_Byte (Value : Byte)
     with Import, Convention => C, External_Name => "tzen_th_feed_b";
   procedure Poll
     with Import, Convention => C, External_Name => "tzen_th_main_function";
   procedure Poll_Worker (Worker : Byte)
     with Import, Convention => C, External_Name => "tzen_th_worker_main_function";
   function Transport_Ok return C_Bool
     with Import, Convention => C, External_Name => "tzen_th_transport_ok";
   function State return Engine_State
     with Import, Convention => C, External_Name => "tzen_get_state";
   function Worker_State (Worker : Byte) return Engine_State
     with Import, Convention => C, External_Name => "tzen_th_worker_get_state";
   function Worker_Count return Interfaces.C.unsigned
     with Import, Convention => C, External_Name => "tzen_ada_worker_count";

   procedure Sync (Ctx : not null Context_Access; Sync_Id : UInt32)
     with Import, Convention => C, External_Name => "tzen_sync";
   function Log
     (Ctx : not null Context_Access; Level : Log_Level; Message : String)
      return C_Bool;
   function Emit_Log
     (Source : UInt32; Execution : access constant Execution_Ref;
      Level : Log_Level; Message : String) return C_Bool;

   type Context_Info is record
      Execution       : Execution_Ref;
      Current_Step    : UInt32;
      Step_Iterations : UInt32;
   end record with Convention => C;

   function Info_For (Ctx : not null Context_Access) return Context_Info;

   --  Size and alignment are in C bytes. The address lasts for this run only.
   --  Access the scratchpad only in callbacks for its owning context.
   function Scratchpad
     (Ctx : not null Context_Access; Size, Alignment : Size_T)
      return System.Address
     with Import, Convention => C, External_Name => "tzen_ada_scratchpad";

private
   --  Ada never allocates or dereferences a C execution context.
   type Context is null record with Convention => C;
end Tzen_Bindings;

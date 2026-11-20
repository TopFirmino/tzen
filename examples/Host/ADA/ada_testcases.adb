--  Tzen
--  Author: L. Furcas
--  SPDX-License-Identifier: MPL-2.0

with Interfaces.C;
with Interfaces.C.Strings;
with System.Address_To_Access_Conversions;

package body Ada_Testcases is
   package Harness renames Tzen_Bindings;
   package C renames Interfaces.C;
   package C_Strings renames Interfaces.C.Strings;
   package Scratch_Byte is new System.Address_To_Access_Conversions (Harness.Byte);
   use type Harness.Byte;
   use type Harness.Size_T;
   use type Harness.UInt32;
   use type Scratch_Byte.Object_Pointer;

   function Count (Ctx : Harness.Context_Access) return Harness.Step_Result
     with Convention => C;
   function Synchronize (Ctx : Harness.Context_Access) return Harness.Step_Result
     with Convention => C;
   function Fail (Ctx : Harness.Context_Access) return Harness.Step_Result
     with Convention => C;

   function Count (Ctx : Harness.Context_Access) return Harness.Step_Result is
      Counter : constant Scratch_Byte.Object_Pointer :=
        Scratch_Byte.To_Pointer
          (Harness.Scratchpad
             (Ctx, Harness.Byte'Object_Size / System.Storage_Unit,
              Harness.Byte'Alignment));
   begin
      if Counter = null
        or else Harness.UInt32 (Counter.all) /= Harness.Info_For (Ctx).Step_Iterations
      then
         return Harness.Step_Fail;
      end if;
      Counter.all := Counter.all + 1;
      if Counter.all < 4 then
         return Harness.Yield;
      end if;
      if Harness.Log (Ctx, Harness.Info, "Yielding test completed") then
         return Harness.Pass_Next;
      end if;
      return Harness.Step_Fail;
   end Count;

   function Synchronize (Ctx : Harness.Context_Access) return Harness.Step_Result is
   begin
      Harness.Sync (Ctx, 42);
      return Harness.Wait_Sync;
   end Synchronize;

   function Fail (Ctx : Harness.Context_Access) return Harness.Step_Result is
      Logged : constant Harness.C_Bool :=
        Harness.Log (Ctx, Harness.Error, "Intentional example failure");
      pragma Unreferenced (Logged);
   begin
      return Harness.Step_Fail;
   end Fail;

   Count_Name : aliased C.char_array := C.To_C ("Yield and pass");
   Sync_Name  : aliased C.char_array := C.To_C ("Synchronize and pass");
   Fail_Name  : aliased C.char_array := C.To_C ("Expected failure");

   Count_Steps : constant Harness.Step_Array := (0 => Count'Access);
   Sync_Steps  : constant Harness.Step_Array := (Synchronize'Access, Count'Access);
   Fail_Steps  : constant Harness.Step_Array := (0 => Fail'Access);

   Tests : constant Harness.Test_Array :=
     ((C_Strings.To_Chars_Ptr (Count_Name'Access), Count_Steps (0)'Access,
       Count_Steps'Length, others => <>),
      (C_Strings.To_Chars_Ptr (Sync_Name'Access), Sync_Steps (0)'Access,
       Sync_Steps'Length, others => <>),
      (C_Strings.To_Chars_Ptr (Fail_Name'Access), Fail_Steps (0)'Access,
       Fail_Steps'Length, others => <>));

   procedure Register (Config : in out Harness.Configuration) is
   begin
      Config.Tests := Tests (Tests'First)'Access;
      Config.Num_Tests := Tests'Length;
   end Register;
end Ada_Testcases;

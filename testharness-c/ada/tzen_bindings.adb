--  Tzen
--  Author: L. Furcas
--  SPDX-License-Identifier: MPL-2.0

package body Tzen_Bindings is
   function C_Log
     (Ctx : Context_Access; Level : Log_Level; Message : System.Address)
      return C_Bool
     with Import, Convention => C, External_Name => "tzen_log";

   function C_Emit_Log
     (Source : UInt32; Execution : access constant Execution_Ref;
      Level : Log_Level; Message : System.Address) return C_Bool
     with Import, Convention => C, External_Name => "tzen_emit_log";

   procedure Read_Context (Ctx : Context_Access; Result : access Context_Info)
     with Import, Convention => C, External_Name => "tzen_ada_context_info";

   function Valid_Message (Message : String) return Boolean is
   begin
      if Message'Length > 63 then
         return False;
      end if;
      for Character_Of_Message of Message loop
         if Character_Of_Message = ASCII.NUL then
            return False;
         end if;
      end loop;
      return True;
   end Valid_Message;

   function Log
     (Ctx : not null Context_Access; Level : Log_Level; Message : String)
      return C_Bool
   is
   begin
      if not Valid_Message (Message) then
         return C_Bool (False);
      end if;
      declare
         Text : constant Interfaces.C.char_array := Interfaces.C.To_C (Message);
      begin
         return C_Log (Ctx, Level, Text'Address);
      end;
   end Log;

   function Emit_Log
     (Source : UInt32; Execution : access constant Execution_Ref;
      Level : Log_Level; Message : String) return C_Bool
   is
   begin
      if not Valid_Message (Message) then
         return C_Bool (False);
      end if;
      declare
         Text : constant Interfaces.C.char_array := Interfaces.C.To_C (Message);
      begin
         return C_Emit_Log (Source, Execution, Level, Text'Address);
      end;
   end Emit_Log;

   function Info_For (Ctx : not null Context_Access) return Context_Info is
      Result : aliased Context_Info;
   begin
      Read_Context (Ctx, Result'Access);
      return Result;
   end Info_For;
end Tzen_Bindings;

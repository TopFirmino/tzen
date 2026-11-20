--  Tzen
--  Author: L. Furcas
--  SPDX-License-Identifier: MPL-2.0

with Ada.Command_Line;
with Ada.Text_IO;
with Ada_Testcases;
with Host_Pipe;
with Interfaces.C;
with Tzen_Bindings;

procedure Tzen_Host_Ada is
   package Harness renames Tzen_Bindings;
   use type Harness.C_Bool;
   use type Interfaces.C.int;
   use type Interfaces.C.unsigned;

   Config : aliased Harness.Configuration :=
     (Send_Bytes => Host_Pipe.Send_Bytes'Access, others => <>);
   System_Source : constant Harness.UInt32 := 1;
   Last_Worker   : constant Interfaces.C.unsigned := Harness.Worker_Count - 1;
   Value         : aliased Harness.Byte;
   Received      : Interfaces.C.int;

   procedure Fail (Message : String) is
   begin
      Ada.Text_IO.Put_Line (Ada.Text_IO.Standard_Error, Message);
      Ada.Command_Line.Set_Exit_Status (Ada.Command_Line.Failure);
   end Fail;
begin
   Ada_Testcases.Register (Config);
   if not Host_Pipe.Init or else not Harness.Init (Config'Access) then
      Fail ("Ada host initialization failed");
      return;
   end if;
   if not Harness.Emit_Log (System_Source, null, Harness.Info, "Ada host ready") then
      Fail ("Could not queue Ada host startup log");
      return;
   end if;

   while Harness.Transport_Ok loop
      Received := Host_Pipe.Read_Byte (Value'Access);
      exit when Received < 0;
      if Received > 0 then
         Harness.Feed_Byte (Value);
      end if;
      Harness.Poll;
      for Worker in 0 .. Last_Worker loop
         Harness.Poll_Worker (Harness.Byte (Worker));
      end loop;
   end loop;

   if not Harness.Transport_Ok then
      Fail ("Ada host transport failed");
   end if;
end Tzen_Host_Ada;

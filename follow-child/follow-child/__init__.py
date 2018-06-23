# -*- coding: utf-8 -*-

# Copyright (c) Jeff Dileo, 2018
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import print_function

import lldb
import traceback
import sys
import time

O_RDONLY = 0x0000
O_WRONLY = 0x0001
O_CREAT  = 0x0200
O_TRUNC  = 0x0400

clear_line = "\x1b[2K\x1b[20D"

inf_loop_x86 = '\xeb\xfe'

fork_start = None
fork_insts = None
fork_end = None
orig_fork_bytes = None

inf_loop_bytes = None
inf_loop_len = None

def __lldb_init_module(debugger, internal_dict):
  # 余の前に人は無く、余の後にも人は無し、我は第六天魔王、織田信長なりぃぃぃぃ
  lldb.command("follow-child")(follow_child_command)

def follow_child_command(dbg, cmdline, res, idict):
  target = dbg.GetSelectedTarget()
  process = target.GetProcess()

  if not process.IsValid():
    print("error: 'follow-child' cannot be used until a target process is attached.")
    return

  scl = target.FindFunctions("fork")
  global fork_start
  global fork_insts
  global fork_end
  global inf_loop_bytes
  global inf_loop_len
  for sc in scl:
    s = sc.GetSymbol()
    fork_start = s.GetStartAddress().GetLoadAddress(target)
    fork_insts = len(s.GetInstructions(target))
    fork_end = s.GetEndAddress().GetLoadAddress(target)
    break

  inf_loop_bytes = inf_loop_x86
  inf_loop_len = len(inf_loop_bytes)

  global orig_fork_bytes
  e = lldb.SBError()
  orig_fork_bytes = process.ReadMemory(fork_end - inf_loop_len, inf_loop_len, e)
  if e.Fail():
    print("error: " + str(e))
    sys.exit(1)

  process.WriteMemory(fork_end - inf_loop_len, inf_loop_bytes, e)

  fork_bp = dbg.GetSelectedTarget().BreakpointCreateByName("fork")
  fork_bp.SetScriptCallbackFunction('__init__.fork_bp_callback')

def fork_bp_callback(frame, bp_loc, dict):
  # note: the moment control goes back to lldb (even for python breakpoint
  #       callbacks) it will print out the prompt line. we do some vt100
  #       shenanigans here to clean that up.
  sys.stdout.write(clear_line)
  sys.stdout.flush()

  # note: breakpoints by name are usually a few bytes from the actual start
  #       in this case, stepping the exact number of them doesn't matter
  #       as extra steps will get caught in the infinite loop
  dbg = lldb.debugger
  async_status = dbg.GetAsync()
  dbg.SetAsync(False)
  target = dbg.GetSelectedTarget()
  process = target.GetProcess()

  bps = []

  for idx in range(target.GetNumBreakpoints()):
    bp = target.GetBreakpointAtIndex(idx)
    if bp.IsEnabled():
      bp.SetEnabled(False)
      bps.append(bp)

  thread = frame.GetThread()

  # note: we can't actually step through as that still results in a bp being
  #       set for the forked copy on return from the syscall

  #for _ in range(fork_insts):
  #  # StepInstruction locks up on infinite loop instructions for some reason
  #  # Therefore we try to detect that condition
  #  lldbrepl = lldb.debugger.GetCommandInterpreter()
  #  res = lldb.SBCommandReturnObject()
  #
  #  lldbrepl.HandleCommand("x/1i $rip", res)
  #  out_str = res.GetOutput()
  #  print(out_str)
  #  bytes = out_str.split(":")[1].strip().split("  ")[0].replace(" ","")
  #  if bytes == inf_loop_bytes.encode('hex'):
  #    break
  #  step_over = True
  #  thread.StepInstruction(step_over)
  #

  # note: instead, we just try to continue, wait some time,
  #       and then catch the loop.
  #       however, at this point we lose the ability to get a frame

  # note: however, SBProcess.Continue() and
  #       SBProcess.Stop()/SendAsyncInterrupt() are broken. using them puts the
  #       SBProcess object in an inconsistent state where the process's
  #       m_public_state (stopped) and m_public_run_lock (locked) do not match.
  #       to get around this utter failing of lldb, we detatch and then
  #       re-attach to the parent while it is caught in the infinite loop,
  #       detaching and re-attaching as necessary until the loop is hit.
  #       it's ghetto, but it works!

  #while True:
  #  thread = dbg.GetSelectedTarget().GetProcess().GetSelectedThread()
  #  print("> loop 1")
  #  target = dbg.GetSelectedTarget()
  #  process = target.GetProcess()
  #  print("> suspended?: " + str(thread.IsSuspended()))
  #  dbg.SetAsync(True)
  #  process.Continue()
  #  process.Stop()
  #  time.sleep(1.0)
  #  dbg.SetAsync(False)
  #  # magic
  #  target = dbg.GetSelectedTarget()
  #  process = target.GetProcess()
  #  process.SendAsyncInterrupt()
  #  time.sleep(0.1)
  #  process.Stop()
  #  process.SendAsyncInterrupt()
  #  time.sleep(0.1)
  #  process.Stop()
  #  #/magic
  #
  #  addr = int(str(thread).split(',')[1].strip().split(' ')[0], 16)
  #  if addr == (fork_end - inf_loop_len):
  #    break
  #
  #while True:
  #  print("> loop 2")
  #  if not process.is_stopped:
  #    print("> not stopped")
  #    process.SendAsyncInterrupt()
  #    #process.Stop()
  #  else:
  #    print("> is stopped")
  #    break

  parent_pid = process.GetProcessID()

  # note: detach, wait, and re-attach in loop until reaching infinite loop

  while True:
    process.Detach() # defaults to keep_stop = false (i.e. continue),
                     # the arg-taking version is not currently in apple lldb
    time.sleep(0.1)
    dbg_listener = dbg.GetListener()
    e = lldb.SBError()
    process = target.AttachToProcessWithID(dbg_listener, parent_pid, e)
    if e.Fail():
      print("error: " + str(e))
      sys.exit(1)

    b = False
    for thread in process:
      frame = thread.GetFrameAtIndex(0)
      if frame.GetPC() == (fork_end - inf_loop_len):
        b = True
        break
    if b:
      break


  e = lldb.SBError()
  process.WriteMemory(fork_end - inf_loop_len, orig_fork_bytes, e)
  if e.Fail():
    print("error: " + str(e))
    sys.exit(1)

  for _ in range(inf_loop_len):
    step_over = True
    thread.StepInstruction(step_over)

  e = lldb.SBError()
  process.WriteMemory(fork_end - inf_loop_len, inf_loop_bytes, e)
  if e.Fail():
    print("error: " + str(e))
    sys.exit(1)

  thread = dbg.GetSelectedTarget().GetProcess().GetSelectedThread()
  active_frame = thread.GetFrameAtIndex(0)
  child_pid = int(active_frame.FindRegister("rax").GetValue(), 16)

  print(("Process {} forked, following child PID {} " +
        "(/tmp/{}.stdin, /tmp/{}.stdout, /tmp/{}.stderr)").format(
        parent_pid, child_pid, child_pid, child_pid, child_pid));

  # note: since the command and behavior are to "follow (the) child," we take
  #       the simple path, and just detach and re-attach to the child.
  #       while lldb, does support having multiple active debugged processes,
  #       implementing this is left as an exercise to the reader.
  #       maybe submit it to PoC||GTFO?
  #
  # note: fwiw, lldb limits you to one process per target, so you'd need to
  #       create a new target based on the parent's one.

  process.Detach()
  dbg_listener = dbg.GetListener()
  e = lldb.SBError()
  process = target.AttachToProcessWithID(dbg_listener, child_pid, e)
  if e.Fail():
    print("error: " + str(e))
    sys.exit(1)


  for bp in bps:
    bp.SetEnabled(True)

  # note: lldb seems to be unable to handle the STDIO streams of a child
  #       process that has copied the descriptors from the parent.
  #       until a good way around this is found, we're just going to
  #       forcibly redirect the streams to disk

  #src = ''
  #src += '(int)dup2((int)open("/dev/stdin", {}), 0);'.format(O_RDONLY)
  #src += '(int)dup2((int)open("/dev/stdout", {}), 1);'.format(O_WRONLY|O_TRUNC)
  #src += '(int)dup2((int)open("/dev/stderr", {}), 2)'.format(O_WRONLY|O_TRUNC)

  src = ''
  src += '(int)dup2((int)open("/tmp/{}.stdin", {}, 0644), 0);'.format(child_pid, O_RDONLY|O_CREAT)
  src += '(int)dup2((int)open("/tmp/{}.stdout", {}, 0644), 1);'.format(child_pid, O_WRONLY|O_TRUNC|O_CREAT)
  src += '(int)dup2((int)open("/tmp/{}.stderr", {}, 0644), 2)'.format(child_pid, O_WRONLY|O_TRUNC|O_CREAT)

  val = target.EvaluateExpression(src)

  # note: attempted to detach and re-attach the child while still in the
  #       infinite loop, but after messing w/ the STDIO descriptors.
  #       that didn't work, but i'm leaving the block here for the future.
  #process.Detach()
  #dbg_listener = dbg.GetListener()
  #e = lldb.SBError()
  #process = target.AttachToProcessWithID(dbg_listener, child_pid, e)
  #if e.Fail():
  #  print("error: " + str(e))
  #  sys.exit(1)

  # note: now clean up the infinite loop in the child

  e = lldb.SBError()
  process.WriteMemory(fork_end - inf_loop_len, orig_fork_bytes, e)
  if e.Fail():
    print("error: " + str(e))
    sys.exit(1)

  thread = None
  for t in process:
    f = t.GetFrameAtIndex(0)
    if f.GetPC() == (fork_end - inf_loop_len):
      thread = t
      break

  for _ in range(inf_loop_len):
    step_over = True
    thread.StepInstruction(step_over)

  e = lldb.SBError()
  process.WriteMemory(fork_end - inf_loop_len, inf_loop_bytes, e)
  if e.Fail():
    print("error: " + str(e))
    sys.exit(1)

  dbg.SetAsync(async_status)

  # escape numbers sourced from source/Host/common/Editline.cpp
  sys.stdout.write(clear_line + "\x1b[2m(lldb)\x1b[22m ")
  sys.stdout.flush()


# -*- coding: utf-8 -*-

# public domain
# (srsly, there isn't even enough code here to copyright)

from os.path import join, dirname
import sys

def __lldb_init_module(debugger, internal_dict):
  # https://github.com/themadcreator/ansir
  with open(join(dirname(__file__), 'magikarp.ansi'), "rb") as fd:
    sys.stdout.write(fd.read())

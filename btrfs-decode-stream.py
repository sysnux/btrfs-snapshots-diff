#! /usr/bin/env python
# -*- coding: utf-8 -*-

from struct import unpack
from sys import argv, exit, stdin, stderr
printerr = stderr.write

# From btrfs/send.h
send_cmds = 'BTRFS_SEND_C_UNSPEC BTRFS_SEND_C_SUBVOL BTRFS_SEND_C_SNAPSHOT BTRFS_SEND_C_MKFILE BTRFS_SEND_C_MKDIR BTRFS_SEND_C_MKNOD BTRFS_SEND_C_MKFIFO BTRFS_SEND_C_MKSOCK BTRFS_SEND_C_SYMLINK BTRFS_SEND_C_RENAME BTRFS_SEND_C_LINK BTRFS_SEND_C_UNLINK BTRFS_SEND_C_RMDIR BTRFS_SEND_C_SET_XATTR BTRFS_SEND_C_REMOVE_XATTR BTRFS_SEND_C_WRITE BTRFS_SEND_C_CLONE BTRFS_SEND_C_TRUNCATE BTRFS_SEND_C_CHMOD BTRFS_SEND_C_CHOWN BTRFS_SEND_C_UTIMES BTRFS_SEND_C_END BTRFS_SEND_C_UPDATE_EXTENT'.split()

send_attrs = 'BTRFS_SEND_A_UNSPEC BTRFS_SEND_A_UUID BTRFS_SEND_A_CTRANSID BTRFS_SEND_A_INO BTRFS_SEND_A_SIZE BTRFS_SEND_A_MODE BTRFS_SEND_A_UID BTRFS_SEND_A_GID BTRFS_SEND_A_RDEV BTRFS_SEND_A_CTIME BTRFS_SEND_A_MTIME BTRFS_SEND_A_ATIME BTRFS_SEND_A_OTIME BTRFS_SEND_A_XATTR_NAME BTRFS_SEND_A_XATTR_DATA BTRFS_SEND_A_PATH BTRFS_SEND_A_PATH_TO BTRFS_SEND_A_PATH_LINK BTRFS_SEND_A_FILE_OFFSET BTRFS_SEND_A_DATA BTRFS_SEND_A_CLONE_UUID BTRFS_SEND_A_CLONE_CTRANSID BTRFS_SEND_A_CLONE_PATH BTRFS_SEND_A_CLONE_OFFSET BTRFS_SEND_A_CLONE_LEN'.split()

# ioctl.h:#define BTRFS_UUID_SIZE 16
BTRFS_UUID_SIZE = 16

if len(argv) != 2:
   print 'Usage %s btrfs_stream_file' % argv[0]
   exit(1)
stream = open(argv[1]).read()

# Global header
idx = 0
l_head = 17
magic, null, version = unpack('<12scI', stream[idx:idx+l_head])
if magic != 'btrfs-stream':
   printerr('Not a Btrfs stream!\n')
   exit(1)
print '"%s" is a Brtfs stream version %d' % (argv[1], version)

# Headers length
l_head = 10
l_tlv = 4

def tlv_get(attr_type, index):
      attr, l_attr = unpack('<HH', stream[index:index+l_tlv])
      if send_attrs[attr] != attr_type:
         raise ValueError('Unexpected attribute %s' % send_attrs[attr])
      ret, = unpack('<H', stream[index+l_tlv:index+l_tlv+l_attr])
      return ret, index + l_tlv + l_attr

def tlv_get_string(attr_type, index):
      attr, l_attr = unpack('<HH', stream[index:index+l_tlv])
      if send_attrs[attr] != attr_type:
         raise ValueError('Unexpected attribute %s' % send_attrs[attr])
      ret, = unpack('<%ds' % l_attr, stream[index+l_tlv:index+l_tlv+l_attr])
      return ret, index + l_tlv + l_attr

def tlv_get_u64(attr_type, index):
      attr, l_attr = unpack('<HH', stream[index:index+l_tlv])
      if send_attrs[attr] != attr_type:
         raise ValueError('Unexpected attribute %s' % send_attrs[attr])
      ret, = unpack('<Q', stream[index+l_tlv:index+l_tlv+l_attr])
      return ret, index + l_tlv + l_attr

def tlv_get_uuid(attr_type, index):
      attr, l_attr = unpack('<HH', stream[index:index+l_tlv])
      if send_attrs[attr] != attr_type:
         raise ValueError('Unexpected attribute %s' % send_attrs[attr])
      ret = unpack('<' + 'B' * BTRFS_UUID_SIZE, stream[index + l_tlv:index + l_tlv + l_attr])
      return ''.join(['%02x' % x for x in ret]), index + l_tlv + l_attr

def tlv_get_timespec(attr_type, index):
      attr, l_attr = unpack('<HH', stream[index:index+l_tlv])
      if send_attrs[attr] != attr_type:
         raise ValueError('Unexpected attribute %s' % send_attrs[attr])
      s, ns = unpack('<QL', stream[index + l_tlv:index + l_tlv + l_attr])
      return '%d.%09d' % (s, ns), index + l_tlv + l_attr

# Decode commands + attributes
l_cmd = 7
count = 0
while True:

   idx += l_head + l_cmd
   count += 1
   res = []

   l_cmd, cmd, crc = unpack('<IHI', stream[idx:idx+l_head])

   if send_cmds[cmd] == 'BTRFS_SEND_C_RENAME':
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(path)
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH_TO', idx2)
      res.append(path)

   elif send_cmds[cmd] == 'BTRFS_SEND_C_SYMLINK':
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(path)
#      path, idx2 = tlv_get_string('BTRFS_SEND_A_INO', idx2) # XXX BTRFS_SEND_A_PATH_LINK in send-stream.c ???
#      res.append(path)

   elif send_cmds[cmd] == 'BTRFS_SEND_C_LINK':
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(path)
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH_LINK', idx2)
      res.append(path)

   elif send_cmds[cmd] == 'BTRFS_SEND_C_UTIMES':
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(path)
      val, idx2 = tlv_get_timespec('BTRFS_SEND_A_ATIME', idx2)
      res.append(val)
      val, idx2 = tlv_get_timespec('BTRFS_SEND_A_MTIME', idx2)
      res.append(val)
      val, idx2 = tlv_get_timespec('BTRFS_SEND_A_CTIME', idx2)
      res.append(val)

   elif send_cmds[cmd] in 'BTRFS_SEND_C_MKFILE BTRFS_SEND_C_MKDIR BTRFS_SEND_C_MKFIFO BTRFS_SEND_C_MKSOCK BTRFS_SEND_C_UNLINK BTRFS_SEND_C_RMDIR '.split():
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(path)

   elif send_cmds[cmd] == 'BTRFS_SEND_C_TRUNCATE':
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(path)
      size, idx2 = tlv_get_u64('BTRFS_SEND_A_SIZE', idx2)
      res.append(str(size))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_SNAPSHOT':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_uuid('BTRFS_SEND_A_UUID', idx2)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_CTRANSID', idx2)
      res.append(str(val))
      val, idx2 = tlv_get_uuid('BTRFS_SEND_A_CLONE_UUID', idx2)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_CLONE_CTRANSID', idx2)
      res.append(str(val))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_SUBVOL':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_uuid('BTRFS_SEND_A_UUID', idx2)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_CTRANSID', idx2)
      res.append(str(val))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_MKNOD':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_MODE', idx2)
      res.append(str(val))
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_RDEV', idx2)
      res.append(str(val))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_SET_XATTR':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_string('BTRFS_SEND_A_XATTR_NAME', idx2)
      res.append(val)
#      val, idx2 = tlv_get('BTRFS_SEND_A_XATTR_DATA', idx2)
#      res.append(val)

   elif send_cmds[cmd] == 'BTRFS_SEND_C_WRITE':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_FILE_OFFSET', idx2)
      res.append(str(val))
#      val, idx2 = tlv_get('BTRFS_SEND_A_XATTR_DATA', idx2)
#      res.append(val)

   elif send_cmds[cmd] == 'BTRFS_SEND_C_REMOVE_XATTR':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_string('BTRFS_SEND_A_XATTR_NAME', idx2)
      res.append(val)

   elif send_cmds[cmd] == 'BTRFS_SEND_C_CLONE':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_FILE_OFFSET', idx2)
      res.append(str(val))
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_CLONE_LEN', idx2)
      res.append(str(val))
      val, idx2 = tlv_get_uuid('BTRFS_SEND_A_CLONE_UUID', idx2)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_CLONE_TRANSID', idx2)
      res.append(str(val))
      val, idx2 = tlv_get_string('BTRFS_SEND_A_CLONE8PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_CLONE_OFFSET', idx2)
      res.append(str(val))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_CHMOD':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_MODE', idx2)
      res.append(str(val))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_CHOWN':
      val, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(val)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_UID', idx2)
      res.append(str(val))
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_GID', idx2)
      res.append(str(val))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_UPDATE_EXTENT':
      path, idx2 = tlv_get_string('BTRFS_SEND_A_PATH', idx+l_head)
      res.append(path)
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_FILE_OFFSET', idx2)
      res.append(str(val))
      val, idx2 = tlv_get_u64('BTRFS_SEND_A_SIZE', idx2)
      res.append(str(val))

   elif send_cmds[cmd] == 'BTRFS_SEND_C_END':
      print 'END: %d commands done (%d = %d ?)' % (count, idx + l_head, len(stream))
      break

   else:
      # Shoud not happen
      raise ValueError('Unexpected command %s' % send_cmds[cmd])

   print '%-14s %s' % (send_cmds[cmd][13:], ', '.join(res))


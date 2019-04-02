#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Displays differences in 2 Btrfs snapshots (from the same subvolume
# obviously).
# Uses btrfs send to compute the differences, decodes the stream and
# displays the differences.
# Can read data from parent and current snapshots, or from diff
# file created with:
# btrfs send -p parent chid --no-data -f /tmp/snaps-diff

# Copyright (c) 2016 Jean-Denis Girard <jd.girard@sysnux.pf>
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


from struct import unpack
from sys import argv, exit, stdin, stderr, exc_info
printerr = stderr.write
import argparse
import subprocess
import time
from collections import OrderedDict
from os import unlink


class BtrfsStream(object):

    # From btrfs/send.h
    send_cmds = 'BTRFS_SEND_C_UNSPEC BTRFS_SEND_C_SUBVOL BTRFS_SEND_C_SNAPSHOT BTRFS_SEND_C_MKFILE BTRFS_SEND_C_MKDIR BTRFS_SEND_C_MKNOD BTRFS_SEND_C_MKFIFO BTRFS_SEND_C_MKSOCK BTRFS_SEND_C_SYMLINK BTRFS_SEND_C_RENAME BTRFS_SEND_C_LINK BTRFS_SEND_C_UNLINK BTRFS_SEND_C_RMDIR BTRFS_SEND_C_SET_XATTR BTRFS_SEND_C_REMOVE_XATTR BTRFS_SEND_C_WRITE BTRFS_SEND_C_CLONE BTRFS_SEND_C_TRUNCATE BTRFS_SEND_C_CHMOD BTRFS_SEND_C_CHOWN BTRFS_SEND_C_UTIMES BTRFS_SEND_C_END BTRFS_SEND_C_UPDATE_EXTENT'.split()

    send_attrs = 'BTRFS_SEND_A_UNSPEC BTRFS_SEND_A_UUID BTRFS_SEND_A_CTRANSID BTRFS_SEND_A_INO BTRFS_SEND_A_SIZE BTRFS_SEND_A_MODE BTRFS_SEND_A_UID BTRFS_SEND_A_GID BTRFS_SEND_A_RDEV BTRFS_SEND_A_CTIME BTRFS_SEND_A_MTIME BTRFS_SEND_A_ATIME BTRFS_SEND_A_OTIME BTRFS_SEND_A_XATTR_NAME BTRFS_SEND_A_XATTR_DATA BTRFS_SEND_A_PATH BTRFS_SEND_A_PATH_TO BTRFS_SEND_A_PATH_LINK BTRFS_SEND_A_FILE_OFFSET BTRFS_SEND_A_DATA BTRFS_SEND_A_CLONE_UUID BTRFS_SEND_A_CLONE_CTRANSID BTRFS_SEND_A_CLONE_PATH BTRFS_SEND_A_CLONE_OFFSET BTRFS_SEND_A_CLONE_LEN'.split()

    # From btrfs/ioctl.h:#define BTRFS_UUID_SIZE 16
    BTRFS_UUID_SIZE = 16

    # Headers length
    l_head = 10
    l_tlv = 4

    def __init__(self, stream_file, delete=False):

        # Read send stream
        try:
            f_stream = open(stream_file)
            self.stream = f_stream.read()
            f_stream.close()

        except:
            printerr('Error reading stream\n')
            exit(1)

        if delete:
            try:
                unlink(stream_file)
            except:
                printerr('Warning: could not delete stream file "%s"\n' %
                         stream_file)

        if len(self.stream) < 17:
            printerr('Invalide stream length\n')
            self.version = None

        magic, null, self.version = unpack('<12scI', self.stream[0:17])
        if magic != 'btrfs-stream':
            printerr('Not a Btrfs stream!\n')
            self.version = None

    def tlv_get(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index:index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError('Unexpected attribute %s' % self.send_attrs[attr])
        ret = unpack('<%dB' % l_attr, self.stream[
                      index + self.l_tlv:index + self.l_tlv + l_attr])
        return index + self.l_tlv + l_attr, ret

    def _tlv_get_string(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index:index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError('Unexpected attribute %s' % self.send_attrs[attr])
        ret, = unpack('<%ds' % l_attr, self.stream[
                      index + self.l_tlv:index + self.l_tlv + l_attr])
        return index + self.l_tlv + l_attr, ret

    def _tlv_get_u64(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index:index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError('Unexpected attribute %s' % self.send_attrs[attr])
        ret, = unpack('<Q', self.stream[
                      index + self.l_tlv:index + self.l_tlv + l_attr])
        return index + self.l_tlv + l_attr, ret

    def _tlv_get_uuid(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index:index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError('Unexpected attribute %s' % self.send_attrs[attr])
        ret = unpack('<%dB' % self.BTRFS_UUID_SIZE,
                     self.stream[index + self.l_tlv:index + self.l_tlv + l_attr])
        return index + self.l_tlv + l_attr, ''.join(['%02x' % x for x in ret])

    def _tlv_get_timespec(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index:index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError('Unexpected attribute %s' % self.send_attrs[attr])
        s, ns = unpack('<QL', self.stream[
                       index + self.l_tlv:index + self.l_tlv + l_attr])
        return index + self.l_tlv + l_attr, float(s) + ns * 1e-9

    def decode(self):
        # Decode commands + attributes
        idx = 17
        count = 0
        # List of commands
        commands = []
        # modified[path] = [(command, cmd_ref), ...]
        modified = OrderedDict()

        while True:

            l_cmd, cmd, crc = unpack(
                '<IHI', self.stream[idx:idx + self.l_head])
            try:
                command = self.send_cmds[cmd]
            except:
                raise ValueError('Unkown command %d' % cmd)

            if command == 'BTRFS_SEND_C_RENAME':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, path_to = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH_TO', idx2)
                # Add bogus renamed_from command on destination to keep track
                # of what happened
                modified.setdefault(path_to, []).append(
                    ('renamed_from', count))
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), path, path_to))

            elif command == 'BTRFS_SEND_C_SYMLINK':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, ino = self._tlv_get_u64('BTRFS_SEND_A_INO', idx2)
                idx2, path_link = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH_LINK', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), path_link))

            elif command == 'BTRFS_SEND_C_LINK':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, path_link = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH_LINK', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), path_link))

            elif command == 'BTRFS_SEND_C_UTIMES':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, atime = self._tlv_get_timespec('BTRFS_SEND_A_ATIME', idx2)
                idx2, mtime = self._tlv_get_timespec('BTRFS_SEND_A_MTIME', idx2)
                idx2, ctime = self._tlv_get_timespec('BTRFS_SEND_A_CTIME', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), atime, mtime, ctime))

            elif command in 'BTRFS_SEND_C_MKFILE BTRFS_SEND_C_MKDIR BTRFS_SEND_C_MKFIFO BTRFS_SEND_C_MKSOCK BTRFS_SEND_C_UNLINK BTRFS_SEND_C_RMDIR '.split():
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower()))

            elif command == 'BTRFS_SEND_C_TRUNCATE':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, size = self._tlv_get_u64('BTRFS_SEND_A_SIZE', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), size))

            elif command == 'BTRFS_SEND_C_SNAPSHOT':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, uuid = self._tlv_get_uuid('BTRFS_SEND_A_UUID', idx2)
                idx2, ctransid = self._tlv_get_u64(
                    'BTRFS_SEND_A_CTRANSID', idx2)
                idx2, clone_uuid = self._tlv_get_uuid(
                    'BTRFS_SEND_A_CLONE_UUID', idx2)
                idx2, clone_ctransid = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_CTRANSID', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), uuid, ctransid,
                                 clone_uuid, clone_ctransid))

            elif command == 'BTRFS_SEND_C_SUBVOL':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, uuid = self._tlv_get_uuid('BTRFS_SEND_A_UUID', idx2)
                idx2, ctransid = self._tlv_get_u64(
                    'BTRFS_SEND_A_CTRANSID', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), uuid, ctransid))

            elif command == 'BTRFS_SEND_C_MKNOD':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, mode = self._tlv_get_u64('BTRFS_SEND_A_MODE', idx2)
                idx2, rdev = self._tlv_get_u64('BTRFS_SEND_A_RDEV', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), mode, rdev))

            elif command == 'BTRFS_SEND_C_SET_XATTR':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, xattr_name = self._tlv_get_string(
                    'BTRFS_SEND_A_XATTR_NAME', idx2)
                idx2, xattr_data = self.tlv_get(
                    'BTRFS_SEND_A_XATTR_DATA', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), xattr_name, xattr_data))

            elif command == 'BTRFS_SEND_C_REMOVE_XATTR':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, xattr_name = self._tlv_get_string(
                    'BTRFS_SEND_A_XATTR_NAME', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), xattr_name))

            elif command == 'BTRFS_SEND_C_WRITE':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, file_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_FILE_OFFSET', idx2)
                idx2, data = self.tlv_get(
                    'BTRFS_SEND_A_DATA', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append(
                    (command[13:].lower(), file_offset, data))

            elif command == 'BTRFS_SEND_C_CLONE':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, file_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_FILE_OFFSET', idx2)
                idx2, clone_len = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_LEN', idx2)
                idx2, clone_uuid = self._tlv_get_uuid(
                    'BTRFS_SEND_A_CLONE_UUID', idx2)
                idx2, clone_transid = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_TRANSID', idx2)
                idx2, clone_path = self._tlv_get_string(
                    'BTRFS_SEND_A_CLONE_PATH', idx + self.l_head)  # BTRFS_SEND_A_CLONE8PATH
                idx2, clone_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_OFFSET', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), file_offset, clone_len,
                                 clone_uuid, clone_transid, clone_path))

            elif command == 'BTRFS_SEND_C_CHMOD':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, mode = self._tlv_get_u64('BTRFS_SEND_A_MODE', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), mode))

            elif command == 'BTRFS_SEND_C_CHOWN':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, uid = self._tlv_get_u64('BTRFS_SEND_A_UID', idx2)
                idx2, gid = self._tlv_get_u64('BTRFS_SEND_A_GID', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), uid, gid))

            elif command == 'BTRFS_SEND_C_UPDATE_EXTENT':
                idx2, path = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH', idx + self.l_head)
                idx2, file_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_FILE_OFFSET', idx2)
                idx2, size = self._tlv_get_u64('BTRFS_SEND_A_SIZE', idx2)
                modified.setdefault(path, []).append(
                    (command[13:].lower(), count))
                commands.append((command[13:].lower(), file_offset, size))

            elif command == 'BTRFS_SEND_C_END':
                commands.append((command[13:].lower(), idx + self.l_head, len(self.stream)))
                break

            elif command == 'BTRFS_SEND_C_UNSPEC':
                pass

            else:
                # Shoud not happen
                raise ValueError('Unexpected command %s' % command)

            idx += self.l_head + l_cmd
            count += 1

        return modified, commands


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
                    description="Display differences between 2 Btrfs snapshots")
    parser.add_argument('-p', '--parent',
                        help='parent snapshot (must exists and be readonly)')
    parser.add_argument('-c', '--child',
                        help='child snapshot (will be created if it does not exist)')
    parser.add_argument('-f', '--file', help="diff file")
    parser.add_argument('-t', '--filter', action='store_true',
                        help='does not display temporary files, nor all time modifications (just latest)')
    parser.add_argument('-s', '--csv', action='store_true',
                        help='CSV output')
#    parser.add_argument('-v', '--verbose', action="count", default=0,
#                        help="increase verbosity")
    args = parser.parse_args()

    if args.parent is not None:
        if args.child is not None:
            # TODO add option to ommit '--no-data'
            stream_file = '/tmp/snaps-diff'
            cmd = ['btrfs', 'send', '-p', args.parent, '--no-data',
                   '-f', stream_file, args.child]
            try:
                subprocess.check_call(cmd)

            except:
                printerr('Error: %s\nexecuting "%s"\n' %
                         (exc_info()[0], ' '.join(cmd)))
                exit(1)
        else:
            printerr('Error: parent needs child!\n')
            parser.print_help()
            exit(1)

    elif args.file is None:
        parser.print_help()
        exit(1)

    else:
        stream_file = args.file

    stream = BtrfsStream(stream_file)
    if stream.version is None:
       exit(1)
    print 'Found a valid Btrfs stream header, version %d' % stream.version
    modified, commands = stream.decode()

    # Temporary files / dirs / links... created by btrfs send: they are later
    # renamed to definitive files / dirs / links...
    if args.filter:
        import re
        re_tmp = re.compile(r'o\d+-\d+-0$')

    for path, actions in modified.iteritems():

        if args.filter and re_tmp.match(path):
            # Don't display files created temporarily and later renamed
            if not (actions[0][0] in ('mkfile', 'mkdir', 'symlink') and \
                    actions[1][0] == 'rename') and \
                    not (actions[0][0] == ('renamed_from') and \
                    actions[1][0] == 'rmdir'):
                print path, '\n\t', actions, '=' * 20
            continue

        if path == '':
            path = '__sub_root__'

        prev_action = None
        extents = []
        print_actions = []

        for a in actions:

            cmd = commands[a[1]]

            if prev_action == 'update_extent' and a[0] != 'update_extent':
                print_actions.append('update extents %d -> %d' % (
                    extents[0][0],
                    extents[-1][0] + extents[-1][1]))

            if a[0] == 'renamed_from':
                if args.filter and re_tmp.match(cmd[1]):
                    if prev_action=='unlink':
                        del(print_actions[-1])
                        print_actions.append('rewritten')
                    else:
                        print_actions.append('created')
                else:
                    print_actions.append('renamed from "%s"' % cmd[1])

            elif a[0] == 'set_xattr':
                print_actions.append('xattr %s %d' % cmd[1:])

            elif a[0] == 'update_extent':
                extents .append(cmd[1:])

            elif a[0] == 'truncate':
                print_actions.append('truncate %d' % cmd[1])

            elif a[0] == 'chown':
                print_actions.append('owner %d:%d' % cmd[1:])

            elif a[0] == 'chmod':
                print_actions.append('mode %o' % cmd[1])

            elif a[0] == 'link':
                print_actions.append('link to "%s"' % cmd[1])

            elif a[0] == 'symlink':
                print_actions.append('symlink to "%s"' % cmd[1])

            elif a[0] in ('unlink', 'mkfile', 'mkdir', 'mkfifo'):
                print_actions.append('%s' % a[0])

            elif a[0] == 'rename':
                print_actions.append('rename to "%s"' % cmd[2])

            elif a[0] == 'utimes':
                if args.filter and prev_action=='utimes':
                   # Print only last utimes
                   del(print_actions[-1])
                print_actions.append('times a=%s m=%s c=%s' % (
                    time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(cmd[1])),
                    time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(cmd[2])),
                    time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(cmd[3]))
                ))

            elif a[0] == 'snapshot':
                print_actions.append(
                    'snapshot: uuid=%s, ctrasid=%d, clone_uuid=%s, clone_ctransid=%d' % cmd[1:])

            elif a[0] == 'write':
                print_actions.append('write: from %d' % cmd[1])
                print_actions.append('data: \n' + ''.join([chr(c) for c in cmd[2]]))  # convert bytes to string

            else:
                print_actions.append('%s, %s %s' % (a, cmd, '-' * 20))
            prev_action = a[0]

        if args.csv:
            print '%s;%s' % (path, ';'.join(print_actions))
        else:
            print '\n%s' % path
            for p in print_actions:
               print '\t%s' % p

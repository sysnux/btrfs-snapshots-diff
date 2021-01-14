#! /usr/bin/env python3
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

''' btrfs-snapshots-diff

Displays differences in 2 Btrfs snapshots (from the same subvolume
obviously).
Uses btrfs send to compute the differences, decodes the stream and
displays the differences.
Can read data from parent and current snapshots, or from diff
file created with:
btrfs send -p parent chid --no-data -f /tmp/snaps-diff


Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


Copyright (c) 2016-2021 Jean-Denis Girard <jd.girard@sysnux.pf>
© SysNux http://www.sysnux.pf/
'''

import time
import argparse
import subprocess
from os import unlink
from sys import exit, stderr  # pylint: disable=redefined-builtin
from struct import unpack
from collections import OrderedDict

printerr = stderr.write


class BtrfsStream:
    ''' Btrfs send stream representation
    '''

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
            with open(stream_file, 'rb') as f_stream:
                self.stream = f_stream.read()

        except IOError:
            printerr('Error reading stream\n')
            exit(1)

        if delete:
            try:
                unlink(stream_file)
            except OSError:
                printerr('Warning: could not delete stream file "{stream_file}"\n')

        if len(self.stream) < 17:
            printerr('Invalide stream length\n')
            self.version = None

        magic, _, self.version = unpack('<12scI', self.stream[0:17])
        if magic != b'btrfs-stream':
            printerr('Not a Btrfs stream!\n')
            self.version = None

    def _tlv_get(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index : index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError(f'Unexpected attribute {self.send_attrs[attr]}')
        ret = unpack(
            f'<{l_attr}B', self.stream[index + self.l_tlv : index + self.l_tlv + l_attr]
        )
        return index + self.l_tlv + l_attr, ret

    def _tlv_get_string(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index : index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError(f'Unexpected attribute {self.send_attrs[attr]}')
        (ret,) = unpack(
            f'<{l_attr}s', self.stream[index + self.l_tlv : index + self.l_tlv + l_attr]
        )
        return index + self.l_tlv + l_attr, ret.decode('utf8')

    def _tlv_get_u64(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index : index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError(f'Unexpected attribute {self.send_attrs[attr]}')
        (ret,) = unpack(
            '<Q', self.stream[index + self.l_tlv : index + self.l_tlv + l_attr]
        )
        return index + self.l_tlv + l_attr, ret

    def _tlv_get_uuid(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index : index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError(f'Unexpected attribute {self.send_attrs[attr]}')
        ret = unpack(
            f'<{self.BTRFS_UUID_SIZE}B',
            self.stream[index + self.l_tlv : index + self.l_tlv + l_attr],
        )
        return index + self.l_tlv + l_attr, ''.join(['%02x' % x for x in ret])

    def _tlv_get_timespec(self, attr_type, index):
        attr, l_attr = unpack('<HH', self.stream[index : index + self.l_tlv])
        if self.send_attrs[attr] != attr_type:
            raise ValueError(f'Unexpected attribute {self.send_attrs[attr]}')
        sec, nanos = unpack(
            '<QL', self.stream[index + self.l_tlv : index + self.l_tlv + l_attr]
        )
        return index + self.l_tlv + l_attr, float(sec) + nanos * 1e-9

    def decode(self, bogus=True):
        ''' Decodes commands + attributes from send stream
        '''
        offset = 17
        cmd_ref = 0
        # List of commands sequentially decoded
        commands = []
        # Modified paths: dict path => [cmd_ref1, cmd_ref2, ...]
        paths = OrderedDict()

        while True:

            # 3rd field is CRC, not used here
            l_cmd, cmd, _ = unpack('<IHI', self.stream[offset : offset + self.l_head])
            try:
                command = self.send_cmds[cmd]
            except IndexError:
                raise ValueError(f'Unkown command {cmd}')

            cmd_short = command[13:].lower()
            offset += self.l_head

            if command == 'BTRFS_SEND_C_RENAME':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, path_to = self._tlv_get_string('BTRFS_SEND_A_PATH_TO', offset2)
                if bogus:
                    # Add bogus renamed_from command on destination to keep track
                    # of what happened
                    paths.setdefault(path_to, []).append(cmd_ref)
                    commands.append(
                        {'command': 'renamed_from', 'path': path, 'path_to': path_to}
                    )
                    cmd_ref += 1
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {'command': cmd_short, 'path': path, 'path_to': path_to}
                )

            elif command == 'BTRFS_SEND_C_SYMLINK':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, ino = self._tlv_get_u64('BTRFS_SEND_A_INO', offset2)
                offset2, path_link = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH_LINK', offset2
                )
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {'command': cmd_short, 'path_link': path_link, 'inode': ino}
                )

            elif command == 'BTRFS_SEND_C_LINK':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, path_link = self._tlv_get_string(
                    'BTRFS_SEND_A_PATH_LINK', offset2
                )
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {'command': cmd_short, 'path': path, 'path_link': path_link}
                )

            elif command == 'BTRFS_SEND_C_UTIMES':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, atime = self._tlv_get_timespec('BTRFS_SEND_A_ATIME', offset2)
                offset2, mtime = self._tlv_get_timespec('BTRFS_SEND_A_MTIME', offset2)
                offset2, ctime = self._tlv_get_timespec('BTRFS_SEND_A_CTIME', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'atime': atime,
                        'mtime': mtime,
                        'ctime': ctime,
                    }
                )

            elif (
                command
                in 'BTRFS_SEND_C_MKFILE BTRFS_SEND_C_MKDIR BTRFS_SEND_C_UNLINK BTRFS_SEND_C_RMDIR'.split()
            ):
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append({'command': cmd_short, 'path': path})

            elif command in 'BTRFS_SEND_C_MKFIFO BTRFS_SEND_C_MKSOCK'.split():
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, ino = self._tlv_get_u64('BTRFS_SEND_A_INO', offset2)
                offset2, rdev = self._tlv_get_u64('BTRFS_SEND_A_RDEV', offset2)
                offset2, mode = self._tlv_get_u64('BTRFS_SEND_A_MODE', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {'command': cmd_short, 'ino': ino, 'path': path, 'rdev': rdev}
                )

            elif command == 'BTRFS_SEND_C_TRUNCATE':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, size = self._tlv_get_u64('BTRFS_SEND_A_SIZE', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append({'command': cmd_short, 'path': path, 'to_size': size})

            elif command == 'BTRFS_SEND_C_SNAPSHOT':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, uuid = self._tlv_get_uuid('BTRFS_SEND_A_UUID', offset2)
                offset2, ctransid = self._tlv_get_u64('BTRFS_SEND_A_CTRANSID', offset2)
                offset2, clone_uuid = self._tlv_get_uuid(
                    'BTRFS_SEND_A_CLONE_UUID', offset2
                )
                offset2, clone_ctransid = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_CTRANSID', offset2
                )
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'uuid': uuid,
                        'ctransid': ctransid,
                        'clone_uuid': clone_uuid,
                        'clone_ctransid': clone_ctransid,
                    }
                )

            elif command == 'BTRFS_SEND_C_SUBVOL':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, uuid = self._tlv_get_uuid('BTRFS_SEND_A_UUID', offset2)
                offset2, ctransid = self._tlv_get_u64('BTRFS_SEND_A_CTRANSID', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'uuid': uuid,
                        'ctrans_id': ctransid,
                    }
                )

            elif command == 'BTRFS_SEND_C_MKNOD':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, mode = self._tlv_get_u64('BTRFS_SEND_A_MODE', offset2)
                offset2, rdev = self._tlv_get_u64('BTRFS_SEND_A_RDEV', offset2)
                commands.append(
                    {'command': cmd_short, 'path': path, 'mode': mode, 'rdev': rdev}
                )

            elif command == 'BTRFS_SEND_C_SET_XATTR':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, xattr_name = self._tlv_get_string(
                    'BTRFS_SEND_A_XATTR_NAME', offset2
                )
                offset2, xattr_data = self._tlv_get('BTRFS_SEND_A_XATTR_DATA', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'xattr_name': xattr_name,
                        'xattr_data': xattr_data,
                    }
                )

            elif command == 'BTRFS_SEND_C_REMOVE_XATTR':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, xattr_name = self._tlv_get_string(
                    'BTRFS_SEND_A_XATTR_NAME', offset2
                )
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {'command': cmd_short, 'path': path, 'xattr_name': xattr_name}
                )

            elif command == 'BTRFS_SEND_C_WRITE':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, file_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_FILE_OFFSET', offset2
                )
                offset2, data = self._tlv_get('BTRFS_SEND_A_DATA', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'file_offset': file_offset,
                        'data': data,
                    }
                )

            elif command == 'BTRFS_SEND_C_CLONE':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, file_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_FILE_OFFSET', offset2
                )
                offset2, clone_len = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_LEN', offset2
                )
                offset2, clone_uuid = self._tlv_get_uuid(
                    'BTRFS_SEND_A_CLONE_UUID', offset2
                )
                offset2, clone_transid = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_TRANSID', offset2
                )
                offset2, clone_path = self._tlv_get_string(
                    'BTRFS_SEND_A_CLONE_PATH', offset
                )  # BTRFS_SEND_A_CLONE8PATH
                offset2, clone_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_CLONE_OFFSET', offset2
                )
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'file_offset': file_offset,
                        'clone_len': clone_len,
                        'clone_uuid': clone_uuid,
                        'clone_transid': clone_transid,
                        'clone_path': clone_path,
                        'clone_offset': clone_offset,
                    }
                )

            elif command == 'BTRFS_SEND_C_CHMOD':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, mode = self._tlv_get_u64('BTRFS_SEND_A_MODE', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append({'command': cmd_short, 'path': path, 'mode': mode})

            elif command == 'BTRFS_SEND_C_CHOWN':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, uid = self._tlv_get_u64('BTRFS_SEND_A_UID', offset2)
                offset2, gid = self._tlv_get_u64('BTRFS_SEND_A_GID', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'user_id': uid,
                        'group_id': gid,
                    }
                )

            elif command == 'BTRFS_SEND_C_UPDATE_EXTENT':
                offset2, path = self._tlv_get_string('BTRFS_SEND_A_PATH', offset)
                offset2, file_offset = self._tlv_get_u64(
                    'BTRFS_SEND_A_FILE_OFFSET', offset2
                )
                offset2, size = self._tlv_get_u64('BTRFS_SEND_A_SIZE', offset2)
                paths.setdefault(path, []).append(cmd_ref)
                commands.append(
                    {
                        'command': cmd_short,
                        'path': path,
                        'file_offset': file_offset,
                        'size': size,
                    }
                )

            elif command == 'BTRFS_SEND_C_END':
                commands.append(
                    {
                        'command': cmd_short,
                        'headers_length': offset,
                        'stream_length': len(self.stream),
                    }
                )
                break

            elif command == 'BTRFS_SEND_C_UNSPEC':
                commands.append({'command': cmd_short})

            else:
                # Shoud not happen!
                raise ValueError(f'Unexpected command "{command}"')

            offset += l_cmd
            cmd_ref += 1

        return commands, paths


def time_str(epoch):
    ''' Epoch => string
    1610391575.9802792 => '2021/01/11 08:59:35' '''
    return time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(epoch))


def print_by_paths(paths, commands, filter, csv):

    # Temporary files / dirs / links... created by btrfs send: they are later
    # renamed to definitive files / dirs / links...
    if filter:
        import re  # pylint: disable=import-outside-toplevel

        re_tmp = re.compile(r'o\d+-\d+-0$')

    for path, actions in paths.items():

        if filter and re_tmp.match(path):
            # Don't display files created temporarily and later renamed
            if not (
                commands[actions[0]]['command'] in ('mkfile', 'mkdir', 'symlink')
                and commands[actions[1]]['command'] == 'rename'
            ) and not (
                commands[actions[0]]['command'] == ('renamed_from')
                and commands[actions[1]]['command'] == 'rmdir'
            ):
                print(f'{path}\n\t{actions} {"=" * 20}')
            continue

        if path == '':
            path = '__sub_root__'

        prev_action = None
        extents = []
        print_actions = []

        for action in actions:

            cmd = commands[action]
            cmd_short = cmd['command']

            if prev_action == 'update_extent' and cmd_short != 'update_extent':
                print_actions.append(
                    'update extents %d -> %d'
                    % (extents[0][0], extents[-1][0] + extents[-1][1])
                )

            if cmd_short == 'renamed_from':
                if filter and re_tmp.match(cmd_short):
                    if prev_action == 'unlink':
                        del print_actions[-1]
                        print_actions.append('rewritten')
                    else:
                        print_actions.append('created')
                else:
                    print_actions.append(f'renamed from "{cmd["path"]}"')

            elif cmd_short == 'set_xattr':
                print_actions.append(f'xattr {cmd["xattr_name"]} {cmd["xattr_data"]}')

            elif cmd_short == 'update_extent':
                extents.append((cmd['file_offset'], cmd['size']))

            elif cmd_short == 'truncate':
                print_actions.append(f'truncate {cmd["to_size"]:d}')

            elif cmd_short == 'chown':
                print_actions.append(f'owner {cmd["user_id"]}:{cmd["group_id"]}')

            elif cmd_short == 'chmod':
                print_actions.append(f'mode {cmd["mode"]:o}')

            elif cmd_short == 'link':
                print_actions.append(f'link to "{cmd["path_link"]}"')

            elif cmd_short == 'symlink':
                print_actions.append(
                    f'symlink to "{cmd["path_link"]}" (inode {cmd["inode"]})'
                )

            elif cmd_short in ('unlink', 'mkfile', 'mkdir', 'mkfifo'):
                print_actions.append(cmd_short)

            elif cmd_short == 'rename':
                print_actions.append(f'rename to "{cmd["path_to"]}')

            elif cmd_short == 'utimes':
                if filter and prev_action == 'utimes':
                    # Print only last utimes
                    del print_actions[-1]
                print_actions.append(
                    f'times a={time_str(cmd["atime"])} '
                    f'm={time_str(cmd["mtime"])} '
                    f'c={time_str(cmd["ctime"])}'
                )

            elif cmd_short == 'snapshot':
                print_actions.append(
                    f'snapshot: uuid={cmd["uuid"]}, '
                    f'ctransid={cmd["ctransid"]:d}, '
                    f'clone_uuid={cmd["clone_uuid"]}, '
                    f'clone_ctransid={cmd["clone_ctransid"]:d}'
                )

            elif cmd_short == 'write':
                print_actions.append('write: from %d' % cmd[1])
                print_actions.append(
                    'data: \n' + ''.join([chr(c) for c in cmd[2]])
                )  # convert bytes to string

            else:
                print_actions.append('%s, %s %s' % (action, cmd, '-' * 20))
            prev_action = cmd_short

            if csv:
                sep = ';'
                esc_sep = '\\' + sep
                print(
                    f'{path.replace(sep, esc_sep)}{sep}'
                    f'{sep.join([a.replace(sep, esc_sep) for a in print_actions])}'
                )
            else:
                print(f'\n{path}')
                for print_action in print_actions:
                    print(f'\t{print_action}')


def main():
    ''' Main ! '''

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Display differences between 2 Btrfs snapshots"
    )
    parser.add_argument(
        '-p', '--parent', help='parent snapshot (must exists and be readonly)'
    )
    parser.add_argument(
        '-c', '--child', help='child snapshot (will be created if it does not exist)'
    )
    parser.add_argument('-f', '--file', help="diff file")
    parser.add_argument(
        '-t',
        '--filter',
        action='store_true',
        help='does not display temporary files, nor all time modifications (just latest)',
    )
    parser.add_argument(
        '-a', '--by_path', action='store_true', help='Group commands by path'
    )
    parser.add_argument('-s', '--csv', action='store_true', help='CSV output')
    parser.add_argument(
        '-j', '--json', action='store_true', help='JSON output (commands only)'
    )
    parser.add_argument(
        '--pretty', action='store_true', help=argparse.SUPPRESS
    )
    parser.add_argument(
        '-b',
        '--bogus',
        action='store_true',
        help='Add bogus renamed_from action (used only when grouping by path)',
    )
    #    parser.add_argument('-v', '--verbose', action="count", default=0,
    #                        help="increase verbosity")
    args = parser.parse_args()

    if args.parent:
        if args.child:
            # TODO add option to ommit '--no-data'
            stream_file = '/tmp/snaps-diff'
            cmd = [
                'btrfs',
                'send',
                '-p',
                args.parent,
                '--no-data',
                '-f',
                stream_file,
                args.child,
                '-q',
            ]
            try:
                subprocess.check_call(cmd)

            except subprocess.CalledProcessError:
                printerr('Error: CalledProcessError\nexecuting "{' '.join(cmd)}"\n')
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
    commands, paths = stream.decode(bogus=args.bogus)

    if args.by_path:
        print(f'Found a valid Btrfs stream header, version {stream.version}\n')
        print_by_paths(paths, commands, args.filter, args.csv)

    elif args.csv:
        sep = ';'
        esc_sep = '\\' + sep
        for cmd in commands:
            print(f'{cmd["command"].replace(sep, esc_sep)}', end='')
            for k in sorted(cmd):
                if k == 'command':
                    continue
                v = cmd[k]
                if isinstance(v, str):
                    v = v.replace(sep, esc_sep)
                print(f'{sep}{k}={v}', end='')
            print()

    elif args.json:
        import json  # pylint: disable=import-outside-toplevel
        if args.pretty:
            print(json.dumps(commands, indent=2))
        else:
            print(json.dumps(commands))            

    else:
        printerr('No output!\n')
        parser.print_help()


if __name__ == '__main__':
    main()

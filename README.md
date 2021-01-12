btrfs-snapshots-diff
====================

About
-----
`btrfs-snapshots-diff.py` is a simple Python2 script that displays the differences 
between two Btrfs snapshots (from the same subvolume obviously).

Uses btrfs send to compute the differences, decodes the stream and 
displays the differences.

Can read data from parent and current snapshots, or from diff file created with:

`btrfs send -p parent chid --no-data -f /tmp/snaps-diff`

Usage
-----
   usage: btrfs-snapshots-diff.py [-h] [-p PARENT] [-c CHILD] [-f FILE] [-t] [-a] [-s] [-j] [-b]

   Display differences between 2 Btrfs snapshots

   optional arguments:
     -h, --help            show this help message and exit
     -p PARENT, --parent PARENT
                        parent snapshot (must exists and be readonly)
     -c CHILD, --child CHILD
                        child snapshot (will be created if it does not exist)
     -f FILE, --file FILE  diff file
     -t, --filter          does not display temporary files, nor all time modifications
                        (just latest)
     -a, --by_path         Group commands by path
     -s, --csv             CSV output
     -j, --json            JSON output (commands only)
     -b, --bogus           Add bogus renamed_from action (used only when grouping by path)


Option `--json` (`-j`), available for commands only, will output a list of 
commands in JSON format.

Option `--csv` (`-s`) will produce on line for each modification, instead of 
formatted output: the first column is the path, then each action taken on the 
file is in a new column. Separator is ";".

Option `--by_path` (`-a`) groups command by path, giving a better view of what 
happenned on the file system.

`--bogus` (`-b`)  adds a bogus command to the stream, to better track renaming of 
files / dir (only usefull with `--by_path`).

With option `--filter` (`-t`), the script tries to be a bit smarter (only usefull 
with `--by_path`):
 * it does not display temporary files created by send stream,
 * it displays 'created' or 'rewritten' on the files renamed from temporary files,
 * it displays only the latest time modifications, if there are two or more.

Example
-------
The example below is the result of creating a new subvolume, taking a 
snapshot (parent), creating some objects ( a file called "file", a 
directory called "dir", fifo, link and symlink...), then taking a new snapshot, 
and last calling btrfs-snapshots-diff to display the differences (see test.sh).

    sudo ./btrfs-snapshots-diff.py -p btrfs-diff-tests.parent -c btrfs-diff-tests.child
    Found a valid Btrfs stream header, version 1
    
    btrfs-diff-tests.child
    	snapshot: uuid=d6515a0a57d462449bcc9c2533d01277, ctrasid=171948, clone_uuid=b66a4f902e348b46b87d4cb85d967ad9, clone_ctransid=171945
    
    __sub_root__
    	times a=2016/04/03 10:36:13 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    	times a=2016/04/03 10:36:13 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    	times a=2016/04/03 10:36:13 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    	times a=2016/04/03 10:36:13 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    	times a=2016/04/03 10:36:13 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    	times a=2016/04/03 10:36:13 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    
    o257-171948-0
    	mkfile
    	rename to "file"
    
    file
    	renamed from "o257-171948-0"
    	xattr security.selinux 28277
    	truncate 0
    	owner 1000:1000
    	mode 664
    	times a=2016/04/03 10:36:15 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    
    hardlink
    	link to "file"
    
    o258-171948-0
    	mkdir
    	rename to "dir"
    
    dir
    	renamed from "o258-171948-0"
    	xattr security.selinux 28277
    	owner 1000:1000
    	mode 775
    	times a=2016/04/03 10:36:15 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    
    o259-171948-0
    	mkfifo
    	rename to "fifo"
    
    fifo
    	renamed from "o259-171948-0"
    	xattr security.selinux 28277
    	owner 1000:1000
    	mode 664
    	times a=2016/04/03 10:36:15 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15
    
    o260-171948-0
    	symlink to "file"
    	rename to "symlink"
    
    symlink
    	renamed from "o260-171948-0"
    	xattr security.selinux 28277
    	owner 1000:1000
    	times a=2016/04/03 10:36:15 m=2016/04/03 10:36:15 c=2016/04/03 10:36:15

Requirements
------------
No requirements besides Python-3!

Bugs
----
There are probably bugs, though it works for me on my own snapshots.


License
-------
GPL v2, see LICENSE file.

Made in beautiful Tahiti (French Polynesia) by [SysNux](http://www.sysnux.pf/ "Systèmes Linux en Polynésie française").

Copyright (c) 2016 Jean-Denis Girard <jd.girard@sysnux.pf>

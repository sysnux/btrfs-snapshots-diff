btrfs-snapshots-diff
====================

About
-----
btrfs-snapshots-diff.py is a  simple Python script that displays the differences 
between 2 Btrfs snapshots (from the same subvolume obviously).

Uses btrfs send to compute the differences, decodes the stream and 
displays the differences.

Can read data from parent and current snapshots, or from diff
file created with:
btrfs send -p parent chid --no-data -f /tmp/snaps-diff

Usage
-----

    usage: btrfs-snapshots-diff.py [-h] [-p PARENT] [-c CHILD] [-f FILE] [-v]
    
    Display differences between 2 Btrfs snapshots
    
    optional arguments:
      -h, --help            show this help message and exit
      -p PARENT, --parent PARENT
                            parent snapshot (must exists and be readonly)
      -c CHILD, --child CHILD
                            child snapshot (will be created if it does not exist)
      -f FILE, --file FILE  diff file
      -v, --verbose         increase verbosity

Requirements
------------
No requirements besides Python-2!


Made in beautiful Tahiti (French Polynesia) by [SysNux](http://wwww.sysnux.pf/).

Copyright (c) 2016 Jean-Denis Girard <jd.girard@sysnux.pf>

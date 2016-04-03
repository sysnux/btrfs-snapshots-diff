# btrfs-snapshots-diff

Displays differences in 2 Btrfs snapshots (from the same subvolume
obviously).
Uses btrfs send to compute the differences, decodes the stream and 
displays the differences.
Can read data from parent and current snapshots, or from diff
file created with:
btrfs send -p parent chid --no-data -f /tmp/snaps-diff

Copyright (c) 2016 Jean-Denis Girard <jd.girard@sysnux.pf>

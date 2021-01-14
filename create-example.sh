#!/bin/bash 
# Note: Use '--inspect' parameter to prevent cleaning up for further inspections.
set -u

test_sub="./btrfs-diff-tests"
old="${test_sub}.parent"
new="${test_sub}.child"

clean_up(){
    echo "Cleaning up temporary subvolumes."
    for sub in $test_sub $old $new; do
        [[ -d $sub ]] && sudo btrfs sub del -c $sub > /dev/null
    done
}

die(){
    echo "ERROR: $@"
    exit 1
}

clean_up
btrfs subvolume create $test_sub
btrfs filesystem sync $test_sub
btrfs subvolume snap -r $test_sub $old
sleep 1
btrfs filesystem sync $old

cd $test_sub
touch file
mkdir dir
mkfifo fifo
ln file hardlink
ln -s file symlink
echo 'Hello Btrfs' > 'xxx;yyy;zzz'
mv file file2
cd ..

btrfs filesystem sync $test_sub
btrfs subvolume snap -r $test_sub $new
btrfs filesystem sync $new

dir=$(pwd)
echo 'btrfs-snapshots-diff.py group by path output:'
echo '============================================='
sudo $dir/btrfs-snapshots-diff.py -p $old -c $new --by_path --bogus --filter
echo

echo 'btrfs-snapshots-diff.py CSV output:'
echo '==================================='
sudo $dir/btrfs-snapshots-diff.py -p $old -c $new --csv
echo

echo 'btrfs-snapshots-diff.py JSON output:'
echo '===================================='
sudo $dir/btrfs-snapshots-diff.py -p $old -c $new --json --pretty
echo

[[ "${1:-}" == "--inspect" ]] || clean_up


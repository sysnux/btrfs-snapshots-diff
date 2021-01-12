
#set -x
function clean_up {
   if [ -d btrfs-diff-tests ] ; then
      sudo btrfs sub del -c ./btrfs-diff-tests
   fi

   if [ -d btrfs-diff-tests.parent ] ; then
      sudo btrfs sub del -c ./btrfs-diff-tests.parent
   fi

   if [ -d btrfs-diff-tests.child ] ; then
      sudo btrfs sub del -c ./btrfs-diff-tests.child
   fi
}

clean_up
btrfs subvolume create ./btrfs-diff-tests
btrfs filesystem sync ./btrfs-diff-tests
btrfs subvolume snap -r ./btrfs-diff-tests ./btrfs-diff-tests.parent
sleep 1
btrfs fil sync ./btrfs-diff-tests.parents

pushd btrfs-diff-tests
touch file
mkdir dir
mkfifo fifo
ln file hardlink
ln -s file symlink
echo 'Hello Btrfs' > 'xxx;yyy;zzz'
mv file file2
popd

btrfs filesystem sync ./btrfs-diff-tests
btrfs subvolume snap -r ./btrfs-diff-tests ./btrfs-diff-tests.child
btrfs filesystem sync ./btrfs-diff-tests.child

dir=$(pwd)
echo 'btrfs-snapshots-diff.py normal output:'
echo '======================================'
sudo $dir/btrfs-snapshots-diff.py -p btrfs-diff-tests.parent -c btrfs-diff-tests.child
echo

echo 'btrfs-snapshots-diff.py CSV output:'
echo '==================================='
sudo $dir/btrfs-snapshots-diff.py -p btrfs-diff-tests.parent -c btrfs-diff-tests.child --csv
echo

clean_up


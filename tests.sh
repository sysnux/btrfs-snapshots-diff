
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
btrfs sub create ./btrfs-diff-tests
btrfs fil sync ./btrfs-diff-tests
btrfs sub snap -r ./btrfs-diff-tests ./btrfs-diff-tests.parent
sleep 1
btrfs fil sync ./btrfs-diff-tests.parents

pushd btrfs-diff-tests
touch file
mkdir dir
mkfifo fifo
ln file hardlink
ln -s file symlink
popd

btrfs fil sync ./btrfs-diff-tests
btrfs sub snap -r ./btrfs-diff-tests ./btrfs-diff-tests.child
btrfs fil sync ./btrfs-diff-tests.child

dir=$(pwd)
sudo $dir/btrfs-snapshots-diff.py -p btrfs-diff-tests.parent -c btrfs-diff-tests.child

clean_up


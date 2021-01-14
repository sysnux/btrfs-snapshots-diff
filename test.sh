#!/bin/bash
set -eu

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

info(){
    echo "INFO: $@"
}

mask(){
    sed -r 's/[0-9]{10}.[0-9]{4,8}/SOME.TIME/g' $1 \
        | sed -r 's/o[0-9]{3}-[0-9]{5}-[0-9]/some_temporary_filename/g' \
        | sed -r 's/[0-9a-f]{32}/some_uuid_here/g' \
        | sed -r 's/ctransid=[0-9]{5}/ctransid=11111/g' \
        | sed -r 's/"ctransid": [0-9]{5}/"ctransid": 11111/' \
        | sed -r 's/"clone_ctransid": [0-9]{5}/"clone_ctransid": 11111/' \
        | sed -r 's|20[0-9]{2}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}|YYYY/mm/dd HH:MM:SS|g'
}

ref="./example.output"
new="./mytest.output"

info "Creating \"$new\""
./create-example.sh > $new

# Simulate a failing test
#echo "hello" >> $new

info "Comparing $ref with $new"
if /usr/bin/diff <(mask $ref) <(mask $new); then
    info "Removing $new"
    rm $new
    echo -e "${GREEN}PASSED: All tests passed succesfully.${NC}"
else
    echo -e "${RED}ERROR: Some tests failed. Please review $new manually.${NC}"
    exit 1
fi

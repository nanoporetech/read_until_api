#!/bin/bash
SEDI="sed -i"
unamestr=`uname`
if [[ "$unamestr" == 'Darwin' ]]; then
  SEDI="sed -i '.bak'"
fi;

for mod in $(ls protobuff/minknow/rpc/ | sed 's/\.proto//');do
  for f in $(ls tmp/*_pb2*.py); do
    hit=$(grep -l "import $mod" $f);
    if [[ $hit ]]; then
      echo "Modifying imports of $hit";
      ${SEDI} "s/import $mod/from\ \.\ import\ $mod/" $f;
    fi;
  done;
done;

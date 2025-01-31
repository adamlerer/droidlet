#!/bin/bash -x
# Copyright (c) Facebook, Inc. and its affiliates.



S3_DEST=s3://craftassist/turk_interactions_with_agent

function background_agent() (
    python3 /droidlet/craftassist/wait_for_cuberite.py --host localhost --port 25565
    python3 /droidlet/craftassist/agent/craftassist_agent.py --no_default_behavior --dev 1>agent.log 2>agent.log
)

python3 /droidlet/craftassist/cuberite_process.py \
    --mode creative \
    --workdir . \
    --config flat_world \
    --seed 0 \
    --logging \
    --add-plugin shutdown_on_leave \
    --add-plugin shutdown_if_no_player_join \
    1>cuberite_process.log \
    2>cuberite_process.log \
    &

background_agent

# if turk_id.txt is provided, write to a turk bucket
if test -f "turk_id.txt"; then
    turk_id="$(cat turk_id.txt)"
    S3_DEST="$S3_DEST/turk/$turk_id"
fi
S3_DEST="$S3_DEST/$TIMESTAMP"

TARBALL=logs.tar.gz
# Only upload the logs and CSV files
find -name "*.log" -o -name "*.csv"|tar czf $TARBALL --force-local -T -

if [ -z "$CRAFTASSIST_NO_UPLOAD" ]; then
    # expects $AWS_ACCESS_KEY_ID and $AWS_SECRET_ACCESS_KEY to exist
    aws s3 cp $TARBALL $S3_DEST/$TARBALL
fi

halt

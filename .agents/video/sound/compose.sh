#!/bin/bash
# Composes the film's score from the composition plan the scene writes (section lengths
# follow the film's beats) with the ElevenLabs music model, in stereo. The plan has no lines and rules out vocals.
# usage: ELEVENLABS_API_KEY=... score/compose.sh plan.json score.mp3 [seed]
set -euo pipefail
cd "$(dirname "$0")"
plan=$1 out=$2 seed=${3:-7}
curl -sf -X POST "https://api.elevenlabs.io/v1/music?output_format=mp3_48000_192" \
    -H "xi-api-key: $ELEVENLABS_API_KEY" -H 'Content-Type: application/json' \
    -d "$(jq -n --slurpfile plan "$plan" --argjson seed "$seed" \
        '{composition_plan: $plan[0], model_id: "music_v1", respect_sections_durations: true, seed: $seed}')" \
    -o "$out" || { rm -f "$out"; echo "failed: $out" >&2; exit 1; }
echo "$out"

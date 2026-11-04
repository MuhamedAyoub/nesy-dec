#!/usr/bin/env bash
# Clone the six Java subjects at the commits of results/SUBJECTS.md (section 2)
# into datasets_java/, the folder java_pipeline/subjects.py reads.
#
#   bash scripts/fetch_subjects.sh            # all six
#   bash scripts/fetch_subjects.sh acmeair    # one, by folder name
#
# Only the CPU stage (facts, resolver, triplets, Sellami export) reads the
# subjects. scripts/reproduce.sh and scripts/replay_decodes.sh do not.
# The builds that write the classpath.txt files are in results/SUBJECTS.md.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${SUBJECTS_DIR:-datasets_java}"
mkdir -p "$DEST"

# folder                                          repository                                         commit
SUBJECTS=(
  "jpetstore-6                                    https://github.com/mybatis/jpetstore-6              ce8015be2c2658d0b657be20328e53045f3a9641"
  "acmeair                                        https://github.com/acmeair/acmeair                  f16122729873ef0449ea276dfb2d2a1d45bebb40"
  "sample.daytrader7                              https://github.com/WASdev/sample.daytrader7         643d04c100f75898003b5c98cde6b5f5015c613a"
  "sample.plantsbywebsphere                       https://github.com/WASdev/sample.plantsbywebsphere  bf5f18b0ba120dfe68a91d7e181c06e32ed6f3c4"
  "KimJongSung__jPetStore                         https://github.com/KimJongSung/jPetStore            bc3fe898326e90658e95f27052ce3004b656d975"
  "SteeleDesmond__sample.mono-to-ms.pbw-monolith  https://github.com/SteeleDesmond/sample.mono-to-ms.pbw-monolith  e6f2a6a437221c2652b907a709cf0343780013f2"
)

for line in "${SUBJECTS[@]}"; do
  read -r dir url commit <<<"$line"
  [[ $# -gt 0 && ! " $* " =~ " $dir " ]] && continue
  if [[ -d "$DEST/$dir/.git" ]]; then
    echo "[fetch] $dir exists, checking out $commit"
  else
    echo "[fetch] $dir <- $url"
    git clone --quiet "$url" "$DEST/$dir"
  fi
  git -C "$DEST/$dir" -c advice.detachedHead=false checkout --quiet "$commit"
  [[ "$(git -C "$DEST/$dir" rev-parse HEAD)" == "$commit" ]] || { echo "[fetch] $dir: wrong commit" >&2; exit 1; }
  echo "[fetch] $dir @ ${commit:0:7} ok"
done

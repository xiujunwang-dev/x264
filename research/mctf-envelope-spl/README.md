# Certified temporal reference omission on official x264

Code and experimental evidence for **Denominator Envelopes for Certified
Temporal Reference Omission**, by **Xiujun Wang**, Independent Researcher.
Contact: xiujunwang.dev@gmail.com. ORCID:
[0009-0006-2773-7936](https://orcid.org/0009-0006-2773-7936).

This research extension is based on official x264 r3223, commit
`0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee`. It is disabled by default and
is not an upstream x264 feature. The measured implementation is for native
macOS ARM64/NEON, eight-bit 4:2:0, and I/P luma filtering.

The repository root on the research branch contains the exact patched
encoder sources. This directory contains the official archive, full patch,
source hashes, tests, replication scripts and compact experimental records.
`source_manifest.json` fixes all 278 encoder source files.

Fixed code snapshot:
[`276cc23474be`](https://github.com/xiujunwang-dev/x264/tree/276cc23474be179214fcdef524bfcc109de5edb9/research/mctf-envelope-spl).
The current research branch may add delivery metadata and packaging updates;
the measured encoder sources and frozen protocol remain unchanged.

## Reproduce

Read [REPRODUCE.txt](REPRODUCE.txt) for the full protocol, dependencies,
input hashes, sanitizer scope and timing exclusions. From this directory:

```sh
python3 restore_and_build.py --destination /absolute/fresh/x264-review --build
python3 prepare_replication.py --build-directory /absolute/fresh/x264-review --inputs /absolute/input-directory --study /absolute/fresh/study
python3 -u /absolute/fresh/study/run_study.py
```

The first command restores a clean official baseline and three extension
builds. Supply the exact six input files specified in `protocol.json`.
The runner verifies input and build hashes. A rerun creates a new study;
do not overwrite the original observations. Run only one timed encoder or
replay at a time, without concurrent compilation or rendering.

The public code export supplies generated table inputs. Full paper sources,
PDFs and the cover letter are delivered separately to the author and journal;
the document-generation commands require those paper sources.

## Reported results and scope

The completed frozen study contains 147 encodes, 295 captured filtered
frames, and 611,712,000 audited pixels per replay method and tolerance.
Blue Sky, Pedestrian Area and Crowd Run are complete native 1080p videos.
All contents had been observed previously; this is a frozen x264 replication.

At tolerance two, the denominator envelope changes filtering time by
**-21.75%** and reference-block work by **-24.96%**, relative to the same
eight-pixel full filter. Complete encoding changes process time by
**-0.93%** and BD-rate by **+0.348%** relative to full MCTF.
The envelope omits the same reference work as tight-radius support at this
tolerance and takes **2.19% more** paired replay time. At tolerance three,
it omits 138,720 additional tile-reference predictions. All certified methods
have zero observed tolerance violations. These are equal-content means
on three contents and one processor, with no significance claim.

The mathematical guarantee compares filter outputs for identical inputs,
motion fields and retained full-window tables. It does not bound the
decoded difference between complete encoders. The finite envelope is a
sufficient certificate; it is not an optimal-subset or exact-worst-error
algorithm. Dinkelbach fractional programming is established prior work.

`summary.json` and `development_summary.json` retain all tolerances,
controls, content results and timing observations. The initial integration
failure and its corrected validation records are retained. Unit tests cover
341,260,850 exhaustive and 4,000,000 random certificate comparisons, plus
kernel boundary tests. The certificate/kernel tests pass ASan/UBSan;
whole-encoder validation claims ASan only.

## Status and provenance

The author has requested submission preparation for IEEE Signal Processing
Letters. No acceptance or completed journal submission is claimed.
Equation-level comparison with three closest unavailable full texts was
deferred by the author; global novelty remains unverified. See
`literature_audit.json` and `publication.json`.

Large original videos, encoded bitstreams, binary snapshots, executable
binaries and build products are excluded. Exact public input URLs and
hashes permit reconstruction. Historical absolute execution paths in JSON
and logs are provenance records, not paths a reviewer must reproduce.

The encoder retains x264's GPL notices and `COPYING`. VVenC-derived
interpolation retains its original notice and pinned attribution in
`encoder/mctf_prior_control.h` at the repository root. Existing notices
apply to their respective files; this export does not relicense third-party
code. OpenAI Codex assisted with derivations, implementation, experiments
and drafting; the author is responsible for scientific content and final
approval.

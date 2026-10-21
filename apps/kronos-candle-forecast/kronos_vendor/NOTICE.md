# Vendored: Kronos model code

`model/` is copied unmodified from https://github.com/shiyu-coder/Kronos
(commit 67b630e, 2026-04-13), file `model/__init__.py`, `model/kronos.py`, `model/module.py`.

Kronos is MIT-licensed, Copyright (c) 2025 ShiYu. The full license text is in
[`LICENSE`](LICENSE) next to this file and must stay with the copied code.

Paper: *Kronos: A Foundation Model for the Language of Financial Markets*
(arXiv:2508.02739, AAAI 2026). Pre-trained weights are downloaded at run time from
https://huggingface.co/NeoQuasar and are not redistributed here.

The upstream repo is not published on PyPI; its README instructs importing the `model`
package from a clone, which is what this demo does (`kronos_demo/forecast.py` puts
this folder on `sys.path`).

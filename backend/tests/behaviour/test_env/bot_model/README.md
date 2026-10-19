# Behaviour classifier

A random forest that judges mouse movement, stroke by stroke, trained on public
human and bot data. The backend uses the exported model
(`app/behaviour/evaluation/mouse_model.json`) to score every behaviour run, as
one of the independent judges next to the lab's own checks, rebrowser and
CreepJS. Results on held-out data are in [REPORT.md](REPORT.md).

## Data

Not committed. Download into `data/` (gitignored):

| Folder | Dataset | Where | Licence |
|---|---|---|---|
| `data/sapimouse/` | SapiMouse, 120 users, human only | <http://www.ms.sapientia.ro/~manyi/sapimouse/sapimouse.zip> - unzip so that `data/sapimouse/sapimouse/user1/...csv` exists | none stated; cite the paper |
| `data/iliou/` | Iliou et al. Web Bot Detection Dataset: humans, moderate bots, advanced bots | <https://m4d.iti.gr/wp-content/uploads/2024/04/web_bot_detection_dataset.zip> - unzip so that `data/iliou/phase1/` and `data/iliou/phase2/` exist | CC BY-NC-SA 2.0 |
| `data/cmu_keystroke/` | CMU keystroke benchmark (Killourhy & Maxion, DSN 2009), 51 typists. Not used for training: `../validate_lab_checks.py` validates the lab's keystroke check on it, and it calibrates the key-hold model in `app/behaviour/primitives/timing.py` | <https://www.cs.cmu.edu/~keystroke/DSL-StrongPasswordData.csv> - save as `data/cmu_keystroke/DSL-StrongPasswordData.csv` | free for research; cite the paper |

**BeCAPTCHA-Mouse** (Acien et al.) is not downloadable without a licence
agreement signed by a permanent member of a research institution
(<https://github.com/BiDAlab/BeCAPTCHA-Mouse>). Its function-based method
(Method 1) is published in full and is re-implemented in `train.py`
(`synthetic_like`); its GAN trajectories are not used. If the benchmark is
obtained, its `DB_fnc/raw` and `DB_GAN/raw` files can be added as further bot
sources.

## Retraining

```bash
cd backend
.venv/Scripts/python.exe -m pip install -r requirements-eval.txt
PYTHONPATH=. .venv/Scripts/python.exe tests/behaviour/test_env/bot_model/train.py
```

About a minute. Rewrites `mouse_model.json` and `REPORT.md`.

## Rules

- Never train on app.behaviour's own output or the robotic control's: the
  classifier is only an independent judge of them if it has not seen them.
- Features live in `app/behaviour/evaluation/mouse_features.py` and are shared
  by training and scoring. Changing them means retraining; the backend refuses
  a model whose feature list does not match.

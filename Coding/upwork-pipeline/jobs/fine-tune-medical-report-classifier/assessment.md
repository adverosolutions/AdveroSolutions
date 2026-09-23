# Private assessment, Fine-Tune an AI Model for a medical report

**NOT for the proposal.**

**Experience gap, say it plainly.** Open-source model fine-tuning is not verified Lorenzo
experience. He works in the Claude API, n8n and Make every day; he has not shipped a
HuggingFace PEFT/LoRA training run that we know of. This is well-trodden ground with
standard tooling (transformers + peft + trl, or a plain classification head on DeBERTa /
DistilBERT), and 800 rows is a small, forgiving dataset, but it is a learning-curve
delivery, not a repeat of something already built. Do not claim a past fine-tuning
project anywhere in the proposal or on camera.

**Time.** 8 to 15 hours over 2 to 4 days. Roughly: 2 to 4h on data cleaning and the
held-out split (this is where the real work is at 800 rows), 1 to 2h on environment and
training format, 2 to 4h on the actual train/eval loop including at least one rerun after
the first numbers come back, 2 to 3h on the inference script, README and reproducibility.
Client says "a few days", which fits, but only if the exact category list arrives on day one.

**Cost.** Free Colab T4 covers 800 rows on a small model comfortably; a rented A10/T4 hour
is roughly $1 to $5 total if he wants headroom. Zero API cost if the model is fully
open-source. Safe to tell the client "no api cost, a few dollars of gpu at most" and
confirm the number once the categories are known.

**Likelihood / what breaks.**
- Label noise. The client already admits "a few mislabeled entries". At 800 rows, 20 bad
  labels move accuracy several points. Suspect rows have to go back to them, and that is a
  dependency on their response time, not on his work.
- Class imbalance on Urgent. Urgent is almost certainly the smallest class and the one that
  matters most. Overall accuracy will look fine while Urgent recall is poor. Grade per
  class or the delivery is misleading.
- De-identification is the client's claim, not a verified fact. Do not process, quote, or
  paste anything that looks identifying. If a row still carries a name, DOB or MRN, stop and
  tell them before continuing. Do not upload the CSV to any third-party API.
- Test set honesty. If the split happens after dedupe/cleaning decisions leak across it, the
  reported improvement is fiction. Split first, then clean the training side.
- 800 rows may simply not be enough for four classes to separate. Real possibility worth
  pricing in; the client did offer more examples, so ask early.

**Standard pricing.** $400 to $1,200 fixed for this scope. Budget was not shown on the post.
He will likely bid at the low end given the learning curve, which is fine, but the
reference number is the range above, not $150.

**Ask before quoting.**
1. The exact category list and a written definition of each, especially where Urgent ends
   and Follow-up needed begins.
2. What hardware they mean by "provided hardware/cloud", do they have a GPU box, a cloud
   account he gets access to, or is Colab on him?
3. Do they need a written reason alongside the label, or just the label? This decides
   classifier head versus small instruct model plus LoRA, and it changes the time estimate.
4. How long the reports are (token length drives model choice and training time).
5. Can they supply more examples for the small classes if Urgent turns out to be thin?

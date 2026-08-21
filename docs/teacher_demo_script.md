# ComplaintGuard Teacher Demonstration Script

This is a presentation script for the supported local, synthetic demonstration.
The preferred live path is conditional: several new registration and Admin
steps remain Emulator-unverified. The static fallback is the safe default until
the local runtime blocker is separately resolved.

## 1. Introduction — 30–60 seconds

**Show:** The architecture summary in `docs/architecture.md` and the local-only
boundary in `docs/demo_guide.md`.

**Say in English:** ComplaintGuard is a bilingual financial complaint workflow.
It helps organize a complaint, suggest a department, send uncertain cases to a
human Manager, and let Staff work within their department. This is a local
Firebase Emulator demonstration with synthetic operational data, not a public
production banking system.

**Myanmar speaking notes:** ComplaintGuard သည် ဘဏ္ဍာရေးတိုင်ကြားချက်များကို
လက်ခံပြီး ဌာနခွဲသို့ ခွဲဝေပေးရန် ကူညီသော ဘာသာစကားနှစ်မျိုးသုံး စနစ်ဖြစ်သည်။
မသေချာသော ကိစ္စများကို Manager က ပြန်လည်စစ်ဆေးရသည်။ ယခုသည် synthetic data
နှင့် local Firebase Emulator ကိုသုံးသော သရုပ်ပြစနစ်ဖြစ်ပြီး production banking
စနစ်မဟုတ်ပါ။

**Reference:** `docs/architecture.md`, `docs/local_setup.md`.

**Do not claim:** Public deployment, production security, or live-user model
performance.

## 2. Problem and objective — 30–45 seconds

**Show:** The six department IDs/labels in `docs/access_matrix.md` and the
workflow diagram in `docs/architecture.md`.

**Say in English:** Manual routing can be inconsistent, and English-only
automation is not sufficient for Myanmar or mixed-language input. The objective
is transparent routing assistance with a safe manual-review path, not perfect
automatic classification.

**Myanmar speaking notes:** လက်ဖြင့် ဌာနခွဲသတ်မှတ်ခြင်းတွင် မတူညီမှုများ
ဖြစ်နိုင်သည်။ မြန်မာဘာသာ သို့မဟုတ် ဘာသာစကားရောနှောသော တိုင်ကြားချက်များကို
အလိုအလျောက်မပို့ဘဲ manual review သို့ ပို့သည်။ ရည်ရွယ်ချက်မှာ ခန့်မှန်းကူညီရန်
ဖြစ်ပြီး အမြဲမှန်မည်ဟု အာမမခံပါ။

**Reference:** `docs/access_matrix.md`, `docs/architecture.md`.

**Do not claim:** Exact right department, zero misrouting, or instant resolution.

## 3. Four roles — 45–60 seconds

**Show:** The role sections in `docs/access_matrix.md`.

**Say in English:** Customers submit and follow their own complaints. Staff work
only on tickets assigned to their department. Managers review uncertain routing,
perform permitted workflow actions, and view model evidence. Admins prepare only
disabled, passwordless, inactive Staff/Manager accounts for separate owner
activation; the bootstrap and activation helpers are committed but unexecuted.
Admin is different from a Firebase Console or Google Cloud owner.

**Myanmar speaking notes:** Customer သည် မိမိတိုင်ကြားချက်ကို တင်ပြီး အခြေအနေကို
ကြည့်နိုင်သည်။ Staff သည် မိမိဌာနခွဲ၏ ticket များကိုသာ လုပ်ဆောင်သည်။ Manager သည်
မသေချာသော routing ကို စစ်ဆေးပြီး workflow နှင့် model evidence ကို ကြည့်သည်။
Admin သည် Staff နှင့် Manager account များကို trusted workflow ဖြင့်သာ ပြင်ဆင်သည်။

**Reference:** `docs/access_matrix.md`, `docs/firestore_schema.md`.

**Do not claim:** Manager can provision accounts, public users can choose roles,
or Admin is the Firebase project owner.

## 4. Complaint workflow — 60–90 seconds

**Show:** If the local environment is already safely operational, use the
existing synthetic Customer, Staff, and Manager workflow. Otherwise show the
workflow description and existing provenance-verified screenshots only; do not
use old screenshots as proof of Slices A–D.

**Say in English:** A Customer submits a complaint through the trusted backend.
The system preserves the original submitted language, applies the routing policy,
and shows the Customer status and messages. Staff see only their department's
queue and can reply or perform permitted transitions. Managers see review work
and can change the final routing without rewriting the original prediction.

**Myanmar speaking notes:** Customer သည် trusted backend မှတစ်ဆင့် တိုင်ကြားချက်
တင်သည်။ စနစ်သည် မူရင်းဘာသာစကားကို ထိန်းသိမ်းပြီး routing policy ကို အသုံးပြုသည်။
Staff သည် မိမိဌာနခွဲ၏ queue ကိုသာ ကြည့်ပြီး reply သို့မဟုတ် ခွင့်ပြုထားသော
အခြေအနေပြောင်းလဲမှုကို လုပ်နိုင်သည်။ Manager သည် review ပြုလုပ်နိုင်ပြီး မူရင်း
prediction ကို မဖျက်ဘဲ final routing ကို ပြောင်းနိုင်သည်။

**Reference:** `docs/firestore_schema.md`, `docs/demo_guide.md`,
`docs/final_test_report.md`.

**Do not claim:** The new UI has been browser-verified if it has not.

## 5. Low-confidence and Myanmar review — 30–45 seconds

**Show:** The routing rule in `ml-api/app/routing.py` and the policy text in
`docs/architecture.md`.

**Say in English:** Supported English at confidence at least `0.60` may route
automatically. Lower confidence goes to manual review. Myanmar and mixed-language
complaints also go to manual review because translation quality was not accepted
as reliable enough for automatic routing.

**Myanmar speaking notes:** English complaint သည် confidence `0.60` သို့မဟုတ်
ထို့ထက်မြင့်လျှင် အလိုအလျောက် routing ပြုလုပ်နိုင်သည်။ confidence နိမ့်လျှင်
manual review သို့ ပို့သည်။ မြန်မာဘာသာနှင့် ဘာသာစကားရောနှောသော complaint များကို
လက်ဖြင့် ပြန်လည်စစ်ဆေးရန် ပို့သည်။

**Reference:** `ml-api/app/routing.py`, `PROJECT_PLAN.md`.

**Do not claim:** Confidence is calibrated probability or that manual review is
a model failure.

## 6. TF-IDF and MultinomialNB — 90–120 seconds

**Show:** The Manager-only Model & Dataset Analytics equations section.

**Say in English:** TF-IDF converts words and word pairs into weighted features.
Repeated terms use a sublinear transform. Rare terms receive more inverse
document weight. The vector is L2-normalized, then MultinomialNB combines class
priors and smoothed feature likelihoods. Because the input is TF-IDF, the feature
weights are not necessarily raw token counts.

**Myanmar speaking notes:** TF-IDF သည် စကားလုံးနှင့် စကားလုံးအတွဲများကို feature
အလေးချိန်များအဖြစ် ပြောင်းလဲသည်။ ထပ်ခါတလဲလဲပါသော စကားလုံးများကို sublinear
နည်းဖြင့် ချိန်ညှိပြီး ရှားပါးသော စကားလုံးများကို ပိုမိုအလေးပေးသည်။ ထို့နောက်
vector ကို L2 normalization ပြုလုပ်ပြီး MultinomialNB ဖြင့် ဌာနခွဲများကို
နှိုင်းယှဉ်သည်။ TF-IDF input ဖြစ်သောကြောင့် feature weight သည် raw token count
ဖြစ်ရန် မလိုပါ။

### Presentation equations

```text
tf(t,d) = 0                                  when count(t,d) = 0
tf(t,d) = 1 + log(count(t,d))                 when count(t,d) > 0

idf(t) = log((1+n)/(1+df(t))) + 1

tfidf(t,d) = tf(t,d) × idf(t)

x̂ = x / sqrt(Σⱼ xⱼ²)

P(t|c) = (N_ct + α) / (Σⱼ N_cj + α|V|),       α = 0.5

score(c,d) = log P(c) + Σₜ x(t,d) log P(t|c)

ŷ = argmax_c score(c,d)
```

Here `t` is a feature, `d` is a normalized complaint, `n` is the training
document count, `df(t)` is document frequency, `c` is one of six departments,
`N_ct` is accumulated TF-IDF feature weight for feature `t` in class `c`, `V`
is the vocabulary, and `α` is smoothing. The committed configuration uses
1–2 word n-grams, `min_df=3`, `max_df=0.98`, at most `100,000` features,
sublinear TF, and L2 normalization.

**Reference:** `frontend/src/components/model-equations.tsx`, frozen model
configuration, `evaluation/day18/model_evaluation_v1.json`.

**Do not claim:** The equations prove live performance or that MultinomialNB
uses only raw token counts.

## 7. Operational threshold — 20–30 seconds

**Show:** The operational routing rule and the confidence section.

**Say in English:** The `0.60` value is an operational safety threshold. It is
not the historical validation-selected threshold `0.0`, and confidence is not
calibrated probability.

**Myanmar speaking notes:** `0.60` သည် လက်ရှိ operational safety threshold
ဖြစ်သည်။ validation မှ ရွေးချယ်ခဲ့သော historical threshold `0.0` နှင့် မတူပါ။
confidence ကို calibrated probability ဟု မယူဆရပါ။

**Reference:** `frontend/src/components/model-equations.tsx`,
`frontend/src/lib/model-evaluation.ts`.

**Do not claim:** `0.60` is an accuracy percentage or calibrated confidence.

## 8. Official frozen evaluation — 45–60 seconds

**Show:** The Frozen held-out offline evaluation card/table.

**Say in English:** On `29,942` held-out test rows, accuracy is `82.7934%`.
Macro-F1 is `0.692345`, below the `0.70` target. The labels are deterministic
Product/Issue mapping proxies, not verified institutional ground truth.

**Myanmar speaking notes:** မူရင်းမှ ခွဲထားသော held-out test row `29,942` တွင်
accuracy သည် `82.7934%` ဖြစ်သည်။ Macro-F1 သည် `0.692345` ဖြစ်ပြီး target `0.70`
အောက်တွင် ရှိသည်။ Label များသည် Product/Issue mapping proxy များဖြစ်ပြီး
အဖွဲ့အစည်း၏ အတည်ပြုထားသော ground truth မဟုတ်ပါ။

**Reference:** `evaluation/day18/model_evaluation_v1.json`,
`docs/model_evaluation.md`.

**Do not claim:** Macro-F1 met the target, or accuracy is live-user accuracy.

## 9. Controlled V1 and V2 evidence — 60–90 seconds

**Show:** The separate V1 and V2 controlled-testing sections and aggregate-safe
case tables. Do not show complaint text.

**Say in English:** V1 is a short-English challenge with classifier matches
`2/6`, automatic coverage `1/6`, correct automatic routes `0/1`, and manual
review `5/6`. V2 is a separately predefined long-English demonstration with
classifier matches `2/6`, automatic coverage `2/6`, correctness among automatic
routes `2/2`, and manual review `4/6`. The V2 `100%` applies only to two
automatically routed cases. It is not overall accuracy, and V1 and V2 are not
combined. No causal claim about complaint length is justified.

**Myanmar speaking notes:** V1 သည် short-English challenge ဖြစ်ပြီး classifier
match `2/6`၊ automatic coverage `1/6`၊ correct automatic route `0/1` နှင့်
manual review `5/6` ဖြစ်သည်။ V2 သည် သီးခြားကြိုတင်သတ်မှတ်ထားသော long-English
demonstration ဖြစ်ပြီး classifier match `2/6`၊ automatic coverage `2/6`၊
automatic route များအတွင်း correctness `2/2` နှင့် manual review `4/6` ဖြစ်သည်။
V2 ၏ `100%` သည် automatic route နှစ်ခုအတွက်သာ ဖြစ်ပြီး overall accuracy မဟုတ်ပါ။
V1 နှင့် V2 ကို မပေါင်းရပါ။

**Reference:** `evaluation/controlled/six_department_synthetic_v1.json`,
`evaluation/controlled/six_department_long_english_supported_use_v2b.json`,
`docs/controlled_synthetic_testing.md`.

**Do not claim:** V2 is overall model accuracy, live-user performance, or proof
that all long English complaints work.

## 10. Honest limitations — 30–45 seconds

**Show:** The limitations section in the Manager evidence view and the current
status in `PROJECT_PLAN.md`.

**Say in English:** The model is frozen, confidence is uncalibrated, and Myanmar
or mixed-language complaints require manual review. New registration and Admin
flows have not been verified against a live Emulator. The UI/UX changes have no
browser visual verification. Cloud deployment, billing, App Check, production
monitoring, backups, retention, rate limiting, and recovery guarantees are
deferred or unavailable.

**Myanmar speaking notes:** Model ကို ပြောင်းလဲထားခြင်း မရှိပါ။ confidence သည်
calibrated မဟုတ်ပါ။ မြန်မာနှင့် ဘာသာစကားရောနှောသော complaint များကို manual review
လိုအပ်သည်။ Registration နှင့် Admin flow အသစ်များကို Emulator တွင် မစမ်းသပ်ရသေးပါ။
Cloud deployment နှင့် production monitoring၊ backup၊ retention၊ rate limiting
တို့ မပြီးသေးပါ။

**Reference:** `PROJECT_PLAN.md`, `docs/local_setup.md`, `docs/demo_guide.md`.

**Do not claim:** Production readiness or completed visual/runtime verification.

## 11. Conclusion — 20–30 seconds

**Show:** The final evidence matrix and the role/access boundary.

**Say in English:** ComplaintGuard demonstrates a transparent local workflow:
customers submit complaints, Staff work within department boundaries, Managers
review uncertainty, and the frozen model provides reproducible evidence. The
main conclusion is useful routing assistance with human review and clearly
labelled limitations, not perfect automation or production deployment.

**Myanmar speaking notes:** ComplaintGuard သည် local workflow ကို ပွင့်လင်းစွာ
သရုပ်ပြသည်။ Customer သည် တင်ပြသည်၊ Staff သည် ဌာနခွဲအလိုက် လုပ်ဆောင်သည်၊
Manager သည် မသေချာမှုကို စစ်ဆေးသည်၊ frozen model သည် ပြန်လည်စစ်ဆေးနိုင်သော
အထောက်အထား ပေးသည်။ ရည်ရွယ်ချက်သည် perfect automation မဟုတ်ဘဲ human review
ပါသော routing assistance ဖြစ်သည်။

**Reference:** `docs/final_submission_evidence.md`, `docs/access_matrix.md`.

**Do not claim:** A production system, a perfect classifier, or a passed live
registration/Admin demonstration.

## Demonstration path decision

### Preferred live path (conditional)

Use only if the already-approved local environment is safely operational:

1. Customer login or registration.
2. Synthetic complaint submission.
3. Automatic routing or manual-review state.
4. Staff queue, reply, and permitted transition.
5. Manager review, analytics, and evidence separation.
6. Admin directory/provisioning explanation without executing owner-only scripts.

Mark all new registration/Admin/provisioning steps as runtime-unverified unless
they have fresh evidence from an approved isolated Emulator session.

### Static fallback path (recommended while blocked)

1. Show `docs/architecture.md` and `docs/access_matrix.md`.
2. Show existing historical workflow evidence without claiming it proves Slices A-D.
3. Show the Manager equations section from the committed component.
4. Show official frozen metrics.
5. Show separate V1 and V2 aggregate-safe tables.
6. Explain role boundaries and limitations from the final evidence matrix.
7. Use screenshots only when their provenance is verified and their privacy review is recorded.

## Final presenter checklist

- [ ] Confirm whether a safe local runtime rehearsal is available.
- [x] Keep the static fallback ready.
- [x] Keep official, V1, and V2 metrics separate.
- [x] State the `0.60` operational threshold and uncalibrated confidence.
- [x] State that Myanmar/mixed-language cases require manual review.
- [x] State that V2 `2/2` is not overall accuracy and has `2/6` coverage.
- [x] Avoid private identifiers, raw complaint text, credentials, and secrets.
- [ ] Complete any new screenshot privacy/provenance review.

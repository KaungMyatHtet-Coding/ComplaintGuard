# ComplaintGuard Presentation Outline

Recommended length: 11 slides plus a 5–8 minute live demo. All screenshots are
placeholders until a passing emulator flow and manual privacy inspection.

## Slide 1 — Title and honest scope

**English slide text**

- ComplaintGuard
- Bilingual financial complaint routing and workflow
- TF-IDF + Multinomial Naive Bayes + Firebase
- Verified local emulator demo

**Visual:** ComplaintGuard home/dashboard hero; synthetic data only.

**Burmese speaker notes:**

ComplaintGuard က ငွေကြေးဆိုင်ရာ တိုင်ကြားချက်တွေကို ဌာနခြောက်ခုထဲ လမ်းကြောင်း
သတ်မှတ်ပေးပြီး Customer, Staff နဲ့ Manager တို့ အဆုံးအထိ ဆောင်ရွက်နိုင်အောင်
ဖန်တီးထားတဲ့ ပညာရေးဆိုင်ရာ demo project ဖြစ်ပါတယ်။ Public production system
မဟုတ်ဘဲ local emulator နဲ့ အတည်ပြုထားတာကို အစကတည်းက ရှင်းပြပါမယ်။

## Slide 2 — Problem, users, and departments

**English slide text:** Manual routing is inconsistent; English-only intake is a
barrier. Users: Customer, Department Staff, Manager. Six proxy departments.

**Visual:** Simple flow from customer to six department cards.

**Burmese notes:**

လူကိုယ်တိုင် ဌာနရွေးရင် မတူညီမှုတွေ ဖြစ်နိုင်ပြီး မြန်မာဘာသာအသုံးပြုသူတွေအတွက်
အင်္ဂလိပ်တစ်မျိုးတည်းက အခက်အခဲဖြစ်ပါတယ်။ ဌာနတွေက တကယ့်ဘဏ် ground truth မဟုတ်ဘဲ
CFPB Product/Issue ကို အခြေခံထားတဲ့ proxy policy ဖြစ်ကြောင်း ပြောပါ။

## Slide 3 — Dataset scale and selection

**English slide text:** 17,034,951 raw snapshot rows → 3,823,413 non-null
narratives → 3,822,576 usable/mapped → 200,000 selected.

**Visual:** Day 19 pipeline card screenshot or recreated aggregate flow.

**Burmese notes:**

၁၇ သန်းလုံးနဲ့ model train လုပ်ထားတာ မဟုတ်ပါဘူး။ Narrative သုံးလို့ရတဲ့ record
တွေကို clean/map လုပ်ပြီး အဲဒီထဲက seed တူတဲ့ ၂၀၀,၀၀၀ sample ကိုသာ modeling
အတွက် ရွေးထားပါတယ်။ Snapshot ရက်စွဲနဲ့ selection bias ကိုလည်း ဖော်ပြပါ။

## Slide 4 — Cleaning, mapping, and imbalance

**English slide text:** Chunked cleaning; conservative PII reduction; labels use
Product/Issue only; Fraud & Security is 72.87% of mapped data.

**Visual:** Existing aggregate Day 6 chart plus six-department distribution.

**Burmese notes:**

Narrative ကို label သတ်မှတ်ဖို့ မသုံးတာက leakage မဖြစ်စေဖို့ အရေးကြီးပါတယ်။
PII redaction က အချို့ obvious pattern တွေကို လျှော့ပေးရုံသာဖြစ်ပြီး anonymization
အာမခံမဟုတ်ပါဘူး။ Class imbalance ကြီးတာကို အားနည်းချက်အဖြစ် ပြပါ။

## Slide 5 — Algorithm and leakage control

**English slide text:** Word 1–2 gram TF-IDF, 100,000 features,
MultinomialNB(alpha=0.5), seed 20260727, duplicate-group split, training-only cap.

**Visual:** Train → validation → held-out test diagram.

**Burmese notes:**

TF-IDF က စာလုံး/စကားစု အရေးပါမှုကို sparse feature အဖြစ်ပြောင်းပြီး Naive Bayes
က ဌာန probability တွေတွက်ပါတယ်။ Vectorizer နဲ့ model ကို training data ပဲ fit
လုပ်ပြီး validation နဲ့ test ကို မသုံးထားကြောင်း ရှင်းပြပါ။

## Slide 6 — Real held-out results

**English slide text:** Accuracy 82.79%; Macro-F1 69.23%; Weighted-F1 83.78%;
target 70% not achieved; held-out test 29,942.

**Visual:** Manager metric cards and per-department table.

**Burmese notes:**

Accuracy က majority class ကြောင့် ကောင်းပုံပေါ်နိုင်ပါတယ်။ Department တစ်ခုစီကို
တန်းတူထားတဲ့ Macro-F1 က ၀.၆၉၂၃၄၅ ဖြစ်ပြီး target ၀.၇၀ ကို မပြည့်ပါဘူး။ ဒီရလဒ်ကို
ပြင်ဆင်မထားဘဲ အမှန်အတိုင်း တင်ပြထားပါတယ်။

## Slide 7 — Error and confidence evidence

**English slide text:** True rows / predicted columns; Transfer recall 43.69%;
0.60 is operational review policy; confidence is not accuracy.

**Visual:** Confusion matrix and confidence-bin screenshot.

**Burmese notes:**

Confusion matrix မှာ row က true label၊ column က predicted label ဖြစ်ပါတယ်။
Transfer precision မြင့်ပေမယ့် recall နိမ့်တာကို ဥပမာပေးပါ။ Confidence က complaint
တစ်ခုရဲ့ uncalibrated output ဖြစ်ပြီး model accuracy မဟုတ်ပါဘူး။

## Slide 8 — System and role workflow

**English slide text:** Auth → trusted API → inference/review → Firestore →
customer/staff/manager workflow.

**Visual:** Current architecture diagram and role screenshots.

**Burmese notes:**

Frontend က မြင်ရ/မမြင်ရကို ထိန်းပေမယ့် security boundary တစ်ခုတည်း မဟုတ်ပါဘူး။
FastAPI က token/role/ownership ကိုစစ်ပြီး Firestore rules က client read/write ကို
ထပ်မံကန့်သတ်ပါတယ်။ Admin က shell သာရှိပြီး operation မရှိပါဘူး။

## Slide 9 — English/Myanmar and manual review

**English slide text:** English may auto-route; low confidence and all
Myanmar/mixed submissions require manager review; translation quality not accepted.

**Visual:** Synthetic Dataset Evidence manual-review panel.

**Burmese notes:**

မြန်မာစာကို translator နဲ့ classifier ဖြတ်နိုင်ပေမယ့် quality threshold မပြည့်တဲ့အတွက်
auto-route မလုပ်ပါဘူး။ Ticket ကို unassigned manual review အဖြစ်ထားပြီး Manager
ကသာ ဌာနပြန်သတ်မှတ်နိုင်ပါတယ်။ Production-ready Myanmar understanding လို့ မပြောပါနဲ့။

## Slide 10 — Security, privacy, and testing

**English slide text:** Customer ownership; exact staff department; manager-only
analytics; deny direct writes; synthetic emulator/E2E evidence; redaction is not anonymity.

**Visual:** Test-layer diagram; no terminal credentials.

**Burmese notes:**

Rules, backend adapter နဲ့ browser E2E စမ်းသပ်မှုတွေက local emulator မှာ role
boundary မှန်ကြောင်းပြပါတယ်။ Production security certification မဟုတ်ပါဘူး။
Retention, rate limiting, monitoring နဲ့ independent audit မရှိသေးတာကို ထည့်ပြောပါ။

## Slide 11 — Demo, limitations, and conclusion

**English slide text:** Demonstrate submission → staff → resolution → feedback →
manager review/analytics. Local-only similarity; no public deployment/admin/QR.

**Visual:** Demo transition card and final evidence chain.

**Burmese notes:**

Project ရဲ့ အားသာချက်က perfect score မဟုတ်ဘဲ raw count ကနေ held-out metric၊
application workflow နဲ့ limitation အထိ ပြန်စစ်နိုင်တဲ့ evidence chain ဖြစ်ပါတယ်။
နောက်တစ်ဆင့်မှာ calibrated confidence, ပိုကောင်းတဲ့ bilingual evaluation,
retention policy နဲ့ production verification လိုအပ်ပါတယ်။

## Live demo transition

“Now I will use only synthetic emulator accounts to show one automatic English
route, the staff/customer resolution flow, one manual-review override, and the
real held-out analytics. No real consumer narrative or credential will appear.”

## Safe screenshot placeholders

1. Customer synthetic ticket with Dataset Evidence.
2. Department-scoped staff ticket detail and synthetic message.
3. Manager low-confidence override modal.
4. Manager held-out metric cards and pipeline.
5. Confusion matrix with caption visible.

Do not create these until emulator E2E passes. Inspect every image at original
resolution and confirm no credential, token, terminal, environment value, real
narrative, or raw Complaint ID is visible.

## Likely questions and evidence-backed answers

**Why Naive Bayes?** It is the required lecture algorithm, transparent, fast on
sparse TF-IDF, CPU-friendly, and reproducible. Its independence and calibration
limitations are acknowledged.

**Was the model trained on 17 million rows?** No. The snapshot had 17,034,951
rows; 3,822,576 were usable/mapped; a fixed 200,000 sample was selected and
68,034 training records were actually fitted.

**Why is weighted F1 higher than macro-F1?** The dataset is strongly imbalanced.
Weighted F1 is dominated by high-support classes; macro-F1 weights all six
departments equally.

**Did you meet the 0.70 target?** No. Held-out macro-F1 is 0.692345 and is
reported without further test-driven tuning.

**Is 90% confidence a 90% chance of correctness?** No. It is an uncalibrated
maximum Naive Bayes output for one prediction.

**How good is Myanmar?** The local pipeline runs, but reviewed translation/routing
quality did not meet acceptance thresholds. Myanmar/mixed tickets always require
manual review.

**Does similarity search 17 million complaints?** No. The ignored local index
covers exactly 29,942 held-out vectors and is not deployed.

**How is authorization enforced?** UI visibility, FastAPI token/role/ownership
checks, and Firestore rules are separate layers tested locally with emulators.

**Is admin implemented?** No. Admin has an authenticated shell only.

**Is it deployed?** No verified public deployment exists. The supported mode is
the local emulator-based academic demonstration.

"use client";

import { useApp } from "@/components/app-provider";
import type { Locale } from "@/lib/i18n";
import { modelEvaluation } from "@/lib/model-evaluation";

type Copy = { title: string; plain: string; mapping: string };
type Equation = { formula: string; en: Copy; my: Copy };

const equations: Equation[] = [
  { formula: "tf(t,d) = 1 + log(count(t,d))  when count(t,d) > 0; otherwise 0", en: { title: "Sublinear term frequency", plain: "Repeated terms matter, but each additional repetition has less effect.", mapping: "t is a word or word pair, d is one normalized complaint, and count(t,d) is its count before the sublinear transform." }, my: { title: "စကားလုံးကြိမ်နှုန်း (Sublinear term frequency)", plain: "စကားလုံးကို ထပ်ခါထပ်ခါ အသုံးပြုခြင်းက အရေးပါသော်လည်း ထပ်တိုးကြိမ်တိုင်း၏ သက်ရောက်မှုကို လျှော့တွက်သည်။", mapping: "t သည် စကားလုံး သို့မဟုတ် စကားလုံးတွဲ၊ d သည် ပုံမှန်ပြုပြင်ထားသော တိုင်ကြားချက်တစ်ခု၊ count(t,d) သည် log မပြောင်းမီ အရေအတွက်ဖြစ်သည်။" } },
  { formula: "idf(t) = log((1+n)/(1+df(t))) + 1", en: { title: "Smoothed inverse document frequency", plain: "A term receives more weight when it appears in fewer training documents; smoothing prevents zero or undefined values.", mapping: "n is the number of training documents and df(t) is the number of training documents containing feature t." }, my: { title: "ချောမွေ့ထားသော ပြောင်းပြန်စာရွက်စာတမ်းကြိမ်နှုန်း", plain: "လေ့ကျင့်စာရွက်စာတမ်း အနည်းငယ်တွင်သာ ပါသော စကားလုံးသည် အလေးချိန်ပိုရပြီး smoothing က သုညတန်ဖိုးကို ကာကွယ်သည်။", mapping: "n သည် လေ့ကျင့်စာရွက်စာတမ်း အရေအတွက်၊ df(t) သည် feature t ပါသော လေ့ကျင့်စာရွက်စာတမ်း အရေအတွက်ဖြစ်သည်။" } },
  { formula: "x(t,d) = tf(t,d) × idf(t)", en: { title: "TF-IDF feature", plain: "The product gives each word or word-pair feature its document-specific weight.", mapping: "x(t,d) is one coordinate in the frozen vectorizer output for complaint d." }, my: { title: "TF-IDF feature", plain: "ဤမြှောက်ခြင်းက တိုင်ကြားချက်တစ်ခုအတွက် စကားလုံး သို့မဟုတ် စကားလုံးတွဲ feature တစ်ခုချင်း၏ အလေးချိန်ကို သတ်မှတ်သည်။", mapping: "x(t,d) သည် တိုင်ကြားချက် d အတွက် frozen vectorizer ထုတ်ပေးသော vector ၏ coordinate တစ်ခုဖြစ်သည်။" } },
  { formula: "x̂ = x / √(Σⱼ xⱼ²)", en: { title: "Configured vector normalization", plain: "After TF-IDF weighting, each non-empty feature vector is L2-normalized so its Euclidean length is one.", mapping: "x is the TF-IDF vector and x̂ is passed to MultinomialNB; this is TfidfVectorizer's default norm='l2'." }, my: { title: "သတ်မှတ်ထားသော vector normalization", plain: "TF-IDF အလေးချိန်ပေးပြီးနောက် feature vector ကို L2 ဖြင့် ပုံမှန်ပြုလုပ်ကာ Euclidean အရှည်ကို တစ်ထားသည်။", mapping: "x သည် TF-IDF vector၊ x̂ သည် MultinomialNB သို့ ပေးသော vector ဖြစ်ပြီး TfidfVectorizer ၏ norm='l2' မူလသတ်မှတ်ချက်ကို အသုံးပြုသည်။" } },
  { formula: "P(c)", en: { title: "Class prior", plain: "Before reading a complaint, this is the learned prior weight for department c.", mapping: "c is one of the six stable department IDs; P(c) is learned from the capped training labels." }, my: { title: "အမျိုးအစား မူလဖြစ်နိုင်ခြေ", plain: "တိုင်ကြားချက်ကို မဖတ်မီ department c ဖြစ်နိုင်မည့် လေ့ကျင့်ထားသော မူလအလေးချိန်ဖြစ်သည်။", mapping: "c သည် သတ်မှတ်ထားသော department ခြောက်ခုထဲမှ တစ်ခု၊ P(c) သည် ကန့်သတ်ထားသော လေ့ကျင့် label များမှ သင်ယူထားသည်။" } },
  { formula: "P(t|c) = (N(t,c) + α) / (N(c) + αV),   α = 0.5", en: { title: "MultinomialNB smoothed likelihood", plain: "Laplace-style smoothing gives every feature a small floor and avoids a zero likelihood.", mapping: "N(t,c) is accumulated training feature weight for t in class c, N(c) is the class feature-weight total, V is vocabulary size, and α is 0.5. With TF-IDF input these are not necessarily raw token counts." }, my: { title: "MultinomialNB ချောမွေ့ထားသော likelihood", plain: "Laplace ပုံစံ smoothing က feature တိုင်းအတွက် အနည်းဆုံးတန်ဖိုးထားပေးသဖြင့် သုည likelihood မဖြစ်စေပါ။", mapping: "N(t,c) သည် class c ထဲရှိ feature t ၏ လေ့ကျင့် feature အလေးချိန်စုစုပေါင်း၊ N(c) သည် class အလေးချိန်စုစုပေါင်း၊ V သည် vocabulary အရွယ်အစား၊ α သည် 0.5 ဖြစ်သည်။ TF-IDF input ဖြစ်သောကြောင့် raw စကားလုံးအရေအတွက်ဟု မဆိုနိုင်ပါ။" } },
  { formula: "score(c,d) = log P(c) + Σₜ x(t,d) log P(t|c)", en: { title: "Class score", plain: "The classifier adds the prior score to the weighted evidence contributed by each feature in the complaint.", mapping: "d is the normalized complaint vector, c is each candidate department, x(t,d) is the normalized TF-IDF feature, and P(t|c) uses α=0.5." }, my: { title: "Class score", plain: "Classifier သည် မူလအလေးချိန်နှင့် တိုင်ကြားချက်ရှိ feature တစ်ခုချင်း၏ အထောက်အထားကို ပေါင်းစပ်သည်။", mapping: "d သည် ပုံမှန်ပြုပြင်ထားသော တိုင်ကြားချက် vector၊ c သည် စမ်းသပ်မည့် department၊ x(t,d) သည် ပုံမှန်ပြု TF-IDF feature၊ P(t|c) တွင် α=0.5 အသုံးပြုသည်။" } },
  { formula: "ŷ = argmax_c score(c,d)", en: { title: "Predicted department", plain: "The predicted department is the candidate with the highest class score.", mapping: "ŷ is one of transfer_payment, account_support, card_atm, fraud_security, loan_credit, or general_support." }, my: { title: "ခန့်မှန်းထားသော department", plain: "Class score အမြင့်ဆုံးရသော department ကို ခန့်မှန်းချက်အဖြစ် ရွေးသည်။", mapping: "ŷ သည် transfer_payment၊ account_support၊ card_atm၊ fraud_security၊ loan_credit သို့မဟုတ် general_support တစ်ခုဖြစ်သည်။" } },
  { formula: "confidence = max_c P(c|d)", en: { title: "Prediction confidence", plain: "Confidence is the largest classifier probability for this one prediction. It is not calibrated probability and does not guarantee correctness.", mapping: "P(c|d) is returned by MultinomialNB predict_proba for complaint d; confidence is not overall accuracy." }, my: { title: "ခန့်မှန်းချက် ယုံကြည်မှု", plain: "Confidence သည် ခန့်မှန်းချက်တစ်ခုအတွက် classifier probability အမြင့်ဆုံးတန်ဖိုးဖြစ်ပြီး calibrated probability မဟုတ်သလို မှန်ကန်မှုကို အာမမခံပါ။", mapping: "P(c|d) သည် တိုင်ကြားချက် d အတွက် MultinomialNB predict_proba ထုတ်ပေးသည့်တန်ဖိုး၊ confidence သည် model accuracy မဟုတ်ပါ။" } },
  { formula: "English ∧ confidence ≥ 0.60 → automatic routing; confidence < 0.60 → manual review; Myanmar or mixed → manual review", en: { title: "Operational routing rule", plain: "Supported English with confidence at least 0.60 may route automatically. Lower confidence, Myanmar, and mixed-language complaints go to manual review.", mapping: "0.60 is the operational policy in routing.py and config.py. The historical validation-selected threshold was 0.0; it is separate and unchanged." }, my: { title: "လုပ်ငန်းသုံး routing စည်းမျဉ်း", plain: "ပံ့ပိုးထားသော English နှင့် confidence 0.60 နှင့်အထက်ကို အလိုအလျောက် route လုပ်နိုင်သည်။ နိမ့်သော confidence၊ မြန်မာနှင့် ဘာသာရော complaint များကို manual review ပို့သည်။", mapping: "0.60 သည် routing.py နှင့် config.py ရှိ လက်ရှိလုပ်ငန်းသုံး policy ဖြစ်သည်။ validation မှ ရွေးထားသော သမိုင်း threshold 0.0 သည် သီးခြားဖြစ်ပြီး မပြောင်းပါ။" } },
  { formula: "Cᵢⱼ = count(y = i and ŷ = j)", en: { title: "Confusion matrix", plain: "Each cell counts cases whose known label is row i and whose predicted label is column j.", mapping: "i and j use the fixed six-department order; y is the proxy true label and ŷ is the model prediction." }, my: { title: "Confusion matrix", plain: "အကွက်တစ်ခုချင်းသည် row i ၏ သိထားသော label နှင့် column j ၏ ခန့်မှန်း label တူညီသော case အရေအတွက်ဖြစ်သည်။", mapping: "i နှင့် j သည် department ခြောက်ခု၏ အစဉ်အတိုင်းဖြစ်ပြီး y သည် proxy true label၊ ŷ သည် model ခန့်မှန်းချက်ဖြစ်သည်။" } },
  { formula: "accuracy = number of correct predictions / total test predictions", en: { title: "Accuracy", plain: "Accuracy is the fraction of frozen held-out test predictions that match their proxy labels.", mapping: "The numerator is the diagonal of C and the denominator is 29,942 held-out test rows." }, my: { title: "Accuracy", plain: "Accuracy သည် frozen held-out test ခန့်မှန်းချက်များအနက် proxy label နှင့် ကိုက်ညီသော အချိုးဖြစ်သည်။", mapping: "အပေါ်ပိုင်းသည် C ၏ diagonal အရေအတွက်၊ အောက်ပိုင်းသည် held-out test row 29,942 ဖြစ်သည်။" } },
  { formula: "precision = TP / (TP + FP)     recall = TP / (TP + FN)", en: { title: "Per-class precision and recall", plain: "Precision asks how trustworthy a class prediction is; recall asks how much of that class was found.", mapping: "TP is true positives, FP is other labels predicted as the class, and FN is the class predicted elsewhere." }, my: { title: "အမျိုးအစားတစ်ခုချင်း Precision နှင့် Recall", plain: "Precision သည် class ခန့်မှန်းချက်၏ ယုံကြည်ရမှု၊ recall သည် ထို class ကို မည်မျှရှာတွေ့သည်ကို ပြသည်။", mapping: "TP သည် မှန်ကန်သော positive၊ FP သည် အခြား label များကို ထို class ဟု ခန့်မှန်းခြင်း၊ FN သည် ထို class ကို အခြားနေရာသို့ ခန့်မှန်းခြင်းဖြစ်သည်။" } },
  { formula: "F1 = 2 × precision × recall / (precision + recall)", en: { title: "Per-class F1", plain: "F1 is the harmonic mean of precision and recall, so both need to be strong for a high score.", mapping: "F1 is calculated separately for each of the six proxy-label departments." }, my: { title: "အမျိုးအစားတစ်ခုချင်း F1", plain: "F1 သည် precision နှင့် recall ၏ harmonic mean ဖြစ်သောကြောင့် နှစ်ခုလုံးကောင်းမှ score မြင့်မည်။", mapping: "F1 ကို proxy-label department ခြောက်ခုအတွက် သီးခြားတွက်ချက်သည်။" } },
  { formula: "macro-F1 = (F1₁ + F1₂ + F1₃ + F1₄ + F1₅ + F1₆) / 6", en: { title: "Macro-F1", plain: "Macro-F1 gives every department equal weight, regardless of test support.", mapping: "The six F1 values follow departmentIds; the frozen result is compared with the 0.70 project target in the evidence table above." }, my: { title: "Macro-F1", plain: "Macro-F1 သည် test row အရေအတွက် မည်မျှရှိသည်ဖြစ်စေ department တစ်ခုချင်းကို တူညီသော အလေးချိန်ပေးသည်။", mapping: "F1 ခြောက်ခုသည် departmentIds အစဉ်နှင့် ကိုက်ညီပြီး frozen result ကို အထက်ပါ evidence table တွင် project target 0.70 နှင့် နှိုင်းယှဉ်ပြထားသည်။" } },
];

export function ModelEquations() {
  const { locale, t } = useApp();
  const metrics = modelEvaluation.metrics;
  return (
    <section className="analytics-card" aria-labelledby="model-how-it-works-title">
      <div className="section-heading">
        <div><p className="eyebrow">{t("modelHowItWorksEyebrow")}</p><h3 id="model-how-it-works-title">{t("modelHowItWorksTitle")}</h3></div>
        <p>{t("modelHowItWorksLead")}</p>
      </div>
      <div className="rounded-xl border border-[var(--line)] bg-[var(--canvas)] p-4 text-sm leading-6">
        <h4 className="font-semibold">{t("modelConfigurationTitle")}</h4>
        <p>{t("modelConfigurationText").replace("{{modelVersion}}", modelEvaluation.metadata.modelVersion)}</p>
        <p className="mt-2">{t("modelEvidenceBoundary")}</p>
      </div>
      <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--canvas)] p-4" tabIndex={0}>
        <h4 className="font-semibold">{t("modelFrozenMetricsTitle")}</h4>
        <p className="mb-3 text-sm leading-6">{t("modelFrozenMetricsLead")}</p>
        <table className="analytics-table min-w-[34rem]">
          <caption>{t("modelFrozenMetricsTitle")}</caption>
          <tbody>
            <tr><th scope="row">{t("modelTestSamples")}</th><td>{modelEvaluation.partitions.test.toLocaleString(locale === "my" ? "my-MM" : "en-US")}</td></tr>
            <tr><th scope="row">{t("modelAccuracy")}</th><td>{metrics.accuracy.toFixed(6)} / {(metrics.accuracy * 100).toFixed(4)}%</td></tr>
            <tr><th scope="row">{t("modelMacroPrecision")}</th><td>{metrics.macro.precision.toFixed(6)}</td></tr>
            <tr><th scope="row">{t("modelMacroRecall")}</th><td>{metrics.macro.recall.toFixed(6)}</td></tr>
            <tr><th scope="row">{t("modelMacroF1")}</th><td>{metrics.macro.f1.toFixed(6)}</td></tr>
            <tr><th scope="row">{t("modelWeightedF1")}</th><td>{metrics.weighted.f1.toFixed(6)}</td></tr>
            <tr><th scope="row">{t("modelBalancedAccuracy")}</th><td>{metrics.balancedAccuracy.toFixed(6)}</td></tr>
          </tbody>
        </table>
        <p className="mt-3 text-sm leading-6">{t("modelMacroTargetDisclosure").replace("{{macroF1}}", metrics.macro.f1.toFixed(6))}</p>
      </div>
      <div className="mt-4 space-y-3">
        {equations.map((equation, index) => {
          const copy = equation[locale as Locale];
          return <details key={equation.formula} className="rounded-xl border border-[var(--line)] bg-[var(--canvas)] p-4" open={index === 0}>
            <summary className="cursor-pointer font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">{copy.title}</summary>
            <div className="mt-3 space-y-3">
              <div className="overflow-x-auto rounded-lg bg-[var(--ink)] p-3 text-[var(--canvas)]" tabIndex={0}><code className="block min-w-max whitespace-pre-wrap break-words font-mono text-sm">{equation.formula}</code></div>
              <p><strong>{t("modelPlainEnglish")}: </strong>{copy.plain}</p>
              <p lang="my"><strong>{t("modelMyanmarExplanation")}: </strong>{equation.my.plain}</p>
              <p><strong>{t("modelImplementationMapping")}: </strong>{copy.mapping}</p>
              <p lang="my"><strong>{t("modelMyanmarMapping")}: </strong>{equation.my.mapping}</p>
            </div>
          </details>;
        })}
      </div>
    </section>
  );
}

export const locales = ["en", "my"] as const;
export type Locale = (typeof locales)[number];

const messages = {
  en: {
    brand: "ComplaintGuard",
    tagline: "Bilingual financial complaint routing",
    loginTitle: "Sign in",
    loginLead: "Use a prepared Firebase demo account.",
    email: "Email",
    password: "Password",
    signIn: "Sign in",
    signingIn: "Signing in…",
    signOut: "Sign out",
    dashboard: "Dashboard",
    loading: "Checking your session…",
    configMissing: "Firebase is not configured on this device.",
    configHelp:
      "Copy .env.example to .env.local and add the approved Firebase Web configuration.",
    authError: "Sign-in failed. Check your credentials and try again.",
    permissionError: "This account is inactive or has no permitted role profile.",
    sensitiveWarning:
      "Never enter a PIN, full account/card number, or other financial secret.",
    demoHelp:
      "Demo identities are prepared in Firebase by the project owner; credentials are never committed.",
    customerShell: "Customer dashboard",
    staffShell: "Department staff dashboard",
    managerShell: "Manager dashboard",
    adminShell: "Administration dashboard",
    foundationOnly:
      "Day 12 provides the authenticated dashboard shell. Complaint workflows begin on their scheduled days.",
    securityBoundary:
      "Navigation is a convenience only. Firestore rules and trusted backend checks enforce authorization.",
    language: "Language",
    english: "English",
    myanmar: "Myanmar",
    complaintEyebrow: "Day 13 submission",
    complaintTitle: "Submit a complaint",
    complaintLead: "Your complaint will be saved securely and classified later.",
    complaintTextLabel: "Complaint",
    complaintSubmit: "Submit complaint",
    complaintSubmitting: "Submitting…",
    complaintRequired: "Enter a complaint before submitting.",
    complaintTooLong: "Complaint must be 5,000 characters or fewer.",
    complaintAuthError: "Your session has expired. Sign in and try again.",
    complaintPermissionError: "Only an active customer account may submit complaints.",
    complaintBackendError: "The complaint could not be saved. Your text is still here; try again.",
    complaintUnexpectedError: "An unexpected error occurred. Your text is still here; try again.",
    complaintSuccess: "Complaint submitted successfully.",
    complaintReference: "Reference ID",
    complaintStatus: "Initial status",
    statusSubmitted: "Submitted",
  },
  my: {
    brand: "ComplaintGuard",
    tagline: "ငွေကြေးဆိုင်ရာ တိုင်ကြားချက် လမ်းကြောင်းခွဲဝေစနစ်",
    loginTitle: "အကောင့်ဝင်ရန်",
    loginLead: "ပြင်ဆင်ထားသော Firebase demo အကောင့်ကို အသုံးပြုပါ။",
    email: "အီးမေးလ်",
    password: "စကားဝှက်",
    signIn: "အကောင့်ဝင်မည်",
    signingIn: "အကောင့်ဝင်နေသည်…",
    signOut: "အကောင့်ထွက်မည်",
    dashboard: "ပင်မစာမျက်နှာ",
    loading: "အကောင့်အခြေအနေ စစ်ဆေးနေသည်…",
    configMissing: "ဤစက်တွင် Firebase configuration မရှိသေးပါ။",
    configHelp:
      ".env.example ကို .env.local အဖြစ်ကူးပြီး အတည်ပြုထားသော Firebase Web configuration ထည့်ပါ။",
    authError: "အကောင့်ဝင်၍ မရပါ။ အချက်အလက်များကို စစ်ဆေးပြီး ထပ်မံကြိုးစားပါ။",
    permissionError: "ဤအကောင့်သည် အသုံးပြုခွင့်ရှိသော role profile မရှိပါ။",
    sensitiveWarning:
      "PIN၊ အကောင့်/ကတ်နံပါတ်အပြည့်အစုံ သို့မဟုတ် ငွေကြေးလျှို့ဝှက်ချက် မထည့်ပါနှင့်။",
    demoHelp:
      "Demo အကောင့်များကို project owner က Firebase တွင် ပြင်ဆင်ရမည်။ စကားဝှက်များကို repository တွင် မသိမ်းပါ။",
    customerShell: "Customer dashboard",
    staffShell: "Department staff dashboard",
    managerShell: "Manager dashboard",
    adminShell: "Administration dashboard",
    foundationOnly:
      "Day 12 တွင် အကောင့်ဝင်ထားသော dashboard အခြေခံကိုသာ ပြုလုပ်ထားသည်။ Complaint လုပ်ငန်းစဉ်များကို သတ်မှတ်ရက်တွင် ဆက်လုပ်မည်။",
    securityBoundary:
      "Navigation သည် အသုံးပြုရလွယ်ကူစေရန်သာ ဖြစ်သည်။ Firestore rules နှင့် trusted backend က access ကို အမှန်တကယ် ကန့်သတ်သည်။",
    language: "ဘာသာစကား",
    english: "English",
    myanmar: "မြန်မာ",
    complaintEyebrow: "Day 13 တိုင်ကြားချက်တင်သွင်းခြင်း",
    complaintTitle: "တိုင်ကြားချက်တင်သွင်းရန်",
    complaintLead: "သင့်တိုင်ကြားချက်ကို လုံခြုံစွာသိမ်းဆည်းပြီး နောက်တစ်ဆင့်တွင် အမျိုးအစားခွဲမည်။",
    complaintTextLabel: "တိုင်ကြားချက်",
    complaintSubmit: "တိုင်ကြားချက်တင်သွင်းမည်",
    complaintSubmitting: "တင်သွင်းနေသည်…",
    complaintRequired: "မတင်သွင်းမီ တိုင်ကြားချက်ရေးပါ။",
    complaintTooLong: "တိုင်ကြားချက်သည် စာလုံးရေ ၅,၀၀၀ ထက်မပိုရပါ။",
    complaintAuthError: "အကောင့်ဝင်ချိန် ကုန်သွားပါပြီ။ ပြန်ဝင်ပြီး ထပ်ကြိုးစားပါ။",
    complaintPermissionError: "အသုံးပြုခွင့်ရှိသော customer အကောင့်သာ တိုင်ကြားနိုင်သည်။",
    complaintBackendError: "တိုင်ကြားချက်ကို မသိမ်းနိုင်ပါ။ ရေးထားသောစာ မပျောက်ပါ။ ထပ်ကြိုးစားပါ။",
    complaintUnexpectedError: "မမျှော်လင့်သော အမှားဖြစ်ပွားသည်။ ရေးထားသောစာ မပျောက်ပါ။ ထပ်ကြိုးစားပါ။",
    complaintSuccess: "တိုင်ကြားချက် အောင်မြင်စွာ တင်သွင်းပြီးပါပြီ။",
    complaintReference: "ရည်ညွှန်းနံပါတ်",
    complaintStatus: "အစအခြေအနေ",
    statusSubmitted: "တင်သွင်းပြီး",
  },
} as const;

export type MessageKey = keyof (typeof messages)["en"];

export function translate(locale: Locale, key: MessageKey): string {
  return messages[locale][key] ?? messages.en[key] ?? `[${key}]`;
}

export function normalizeLocale(value: unknown): Locale {
  return value === "my" ? "my" : "en";
}

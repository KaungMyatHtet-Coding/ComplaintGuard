"use client";

import { doc, getDoc } from "firebase/firestore";
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
} from "firebase/auth";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { parseUserProfile, validateCredentials, type UserProfile } from "@/lib/auth-policy";
import { getFirebaseServices, hasFirebaseConfig } from "@/lib/firebase";
import { normalizeLocale, translate, type Locale, type MessageKey } from "@/lib/i18n";

type AuthStatus =
  | "loading"
  | "unauthenticated"
  | "authenticated"
  | "configuration_missing"
  | "error";

type AppContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey) => string;
  status: AuthStatus;
  profile: UserProfile | null;
  errorCode: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AppContext = createContext<AppContextValue | null>(null);

function safeErrorCode(error: unknown): string {
  if (error instanceof Error) {
    if (error.message.startsWith("profile_") || error.message.startsWith("firebase_")) {
      return error.message;
    }
  }
  return "authentication_failed";
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  useEffect(() => {
    const storedLocale = normalizeLocale(
      window.localStorage.getItem("complaintguard.locale"),
    );
    queueMicrotask(() => setLocaleState(storedLocale));
    if (!hasFirebaseConfig()) {
      queueMicrotask(() => setStatus("configuration_missing"));
      return;
    }
    const { auth, db } = getFirebaseServices();
    return onAuthStateChanged(auth, async (user) => {
      if (!user) {
        setProfile(null);
        setStatus("unauthenticated");
        return;
      }
      try {
        const snapshot = await getDoc(doc(db, "users", user.uid));
        const nextProfile = parseUserProfile(
          user.uid,
          user.email ?? "",
          snapshot.exists() ? snapshot.data() : null,
        );
        setProfile(nextProfile);
        setLocaleState(nextProfile.locale);
        setErrorCode(null);
        setStatus("authenticated");
      } catch (error) {
        setProfile(null);
        const nextErrorCode = safeErrorCode(error);
        await firebaseSignOut(auth);
        setErrorCode(nextErrorCode);
        setStatus("error");
      }
    });
  }, []);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
    window.localStorage.setItem("complaintguard.locale", nextLocale);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const checked = validateCredentials(email, password);
    if (!checked.valid) {
      setErrorCode(checked.code);
      setStatus("error");
      return;
    }
    if (!hasFirebaseConfig()) {
      setErrorCode("firebase_configuration_missing");
      setStatus("configuration_missing");
      return;
    }
    setStatus("loading");
    setErrorCode(null);
    try {
      const { auth } = getFirebaseServices();
      await signInWithEmailAndPassword(auth, checked.email, password);
    } catch {
      setErrorCode("authentication_failed");
      setStatus("error");
    }
  }, []);

  const signOut = useCallback(async () => {
    if (!hasFirebaseConfig()) return;
    await firebaseSignOut(getFirebaseServices().auth);
    setProfile(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo<AppContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key) => translate(locale, key),
      status,
      profile,
      errorCode,
      signIn,
      signOut,
    }),
    [errorCode, locale, profile, setLocale, signIn, signOut, status],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used within AppProvider");
  return value;
}

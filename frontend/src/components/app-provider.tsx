"use client";

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
  useRef,
  useState,
} from "react";

import { validateCredentials, type UserProfile } from "@/lib/auth-policy";
import {
  completeCustomerProfile as completeCustomerProfileRequest,
  CustomerProfileError,
  type CustomerProfileCompletionInput,
} from "@/lib/customer-profile";
import { loadAuthenticatedProfile } from "@/lib/auth-profile";
import { getFirebaseServices, hasFirebaseConfig } from "@/lib/firebase";
import { normalizeLocale, translate, type Locale, type MessageKey } from "@/lib/i18n";

export type AuthStatus =
  | "loading"
  | "unauthenticated"
  | "authenticated"
  | "configuration_missing"
  | "error"
  | "profile_incomplete"
  | "profile_inactive"
  | "profile_malformed"
  | "profile_unavailable"
  | "profile_completion_pending";

type AppContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey) => string;
  status: AuthStatus;
  profile: UserProfile | null;
  errorCode: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  completeCustomerProfile: (input: CustomerProfileCompletionInput) => Promise<void>;
  profileCompletionPending: boolean;
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
  const [profileCompletionPending, setProfileCompletionPending] = useState(false);
  const activeUidRef = useRef<string | null>(null);
  const authStatusRef = useRef<AuthStatus>("loading");
  const authErrorCodeRef = useRef<string | null>(null);
  const authGenerationRef = useRef(0);
  const completionRef = useRef<Promise<void> | null>(null);
  authStatusRef.current = status;
  authErrorCodeRef.current = errorCode;

  useEffect(() => {
    const storedLocale = normalizeLocale(
      window.localStorage.getItem("complaintguard.locale"),
    );
    queueMicrotask(() => setLocaleState(storedLocale));
    if (!hasFirebaseConfig()) {
      queueMicrotask(() => setStatus("configuration_missing"));
      return;
    }
    let services: ReturnType<typeof getFirebaseServices>;
    try {
      services = getFirebaseServices();
    } catch (error) {
      queueMicrotask(() => {
        setErrorCode(safeErrorCode(error));
        setStatus("configuration_missing");
      });
      return;
    }
    const { auth, db } = services;
    return onAuthStateChanged(auth, async (user) => {
      const generation = ++authGenerationRef.current;
      activeUidRef.current = user?.uid ?? null;
      setProfile(null);
      setErrorCode(null);
      setProfileCompletionPending(false);
      if (!user) {
        setStatus("unauthenticated");
        return;
      }
      const resolution = await loadAuthenticatedProfile(user, db);
      if (generation !== authGenerationRef.current) return;
      if (resolution.kind === "valid") {
        setProfile(resolution.profile);
        setLocaleState(resolution.profile.locale);
        setStatus("authenticated");
      } else if (resolution.kind === "missing") {
        setErrorCode("profile_incomplete");
        setStatus("profile_incomplete");
      } else if (resolution.kind === "unavailable") {
        setErrorCode("profile_lookup_unavailable");
        setStatus("profile_unavailable");
      } else if (resolution.kind === "inactive") {
        setErrorCode("profile_inactive");
        setStatus("profile_inactive");
      } else {
        setErrorCode("profile_malformed");
        setStatus("profile_malformed");
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

  const completeCustomerProfile = useCallback(
    async (input: CustomerProfileCompletionInput) => {
      if (completionRef.current) return completionRef.current;
      const operation = (async () => {
        if (!hasFirebaseConfig()) {
          setErrorCode("firebase_configuration_missing");
          setStatus("configuration_missing");
          return;
        }
        let auth: ReturnType<typeof getFirebaseServices>["auth"];
        let db: ReturnType<typeof getFirebaseServices>["db"];
        try {
          ({ auth, db } = getFirebaseServices());
        } catch (error) {
          setErrorCode(safeErrorCode(error));
          setStatus("configuration_missing");
          return;
        }
        const user = auth.currentUser;
        if (!user || activeUidRef.current !== user.uid) {
          setProfile(null);
          setErrorCode("authentication_required");
          setStatus("unauthenticated");
          return;
        }
        const canCompleteProfile =
          authStatusRef.current === "profile_incomplete" ||
          (authStatusRef.current === "profile_unavailable" &&
            authErrorCodeRef.current === "profile_completion_unavailable");
        if (!canCompleteProfile) return;
        setProfileCompletionPending(true);
        setStatus("profile_completion_pending");
        try {
          await completeCustomerProfileRequest(user, input);
        } catch (error) {
          if (error instanceof CustomerProfileError) {
            if (error.code === "auth") {
              await firebaseSignOut(auth);
              setProfile(null);
              setErrorCode("authentication_required");
              setStatus("unauthenticated");
            } else if (error.code === "conflict") {
              setErrorCode("profile_conflict");
              setStatus("profile_malformed");
            } else if (error.code === "invalid_input" || error.code === "validation") {
              setErrorCode("profile_completion_invalid");
              setStatus("profile_incomplete");
            } else {
              setErrorCode("profile_completion_unavailable");
              setStatus("profile_unavailable");
            }
          } else {
            setErrorCode("profile_completion_unavailable");
            setStatus("profile_unavailable");
          }
          return;
        }
        if (activeUidRef.current !== user.uid || auth.currentUser?.uid !== user.uid) {
          return;
        }
        try {
          const resolution = await loadAuthenticatedProfile(user, db);
          if (resolution.kind === "valid") {
            setProfile(resolution.profile);
            setLocaleState(resolution.profile.locale);
            setErrorCode(null);
            setStatus("authenticated");
          } else if (resolution.kind === "missing") {
            setErrorCode("profile_incomplete");
            setStatus("profile_incomplete");
          } else if (resolution.kind === "unavailable") {
            setErrorCode("profile_lookup_unavailable");
            setStatus("profile_unavailable");
          } else if (resolution.kind === "inactive") {
            setErrorCode("profile_inactive");
            setStatus("profile_inactive");
          } else {
            setErrorCode("profile_malformed");
            setStatus("profile_malformed");
          }
        } catch {
          setErrorCode("profile_lookup_unavailable");
          setStatus("profile_unavailable");
        }
      })();
      completionRef.current = operation;
      try {
        await operation;
      } finally {
        if (completionRef.current === operation) {
          completionRef.current = null;
          setProfileCompletionPending(false);
        }
      }
    },
    [],
  );

  const signOut = useCallback(async () => {
    if (hasFirebaseConfig()) {
      await firebaseSignOut(getFirebaseServices().auth);
    }
    activeUidRef.current = null;
    setProfile(null);
    setErrorCode(null);
    setProfileCompletionPending(false);
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
      completeCustomerProfile,
      profileCompletionPending,
      signOut,
    }),
    [
      completeCustomerProfile,
      errorCode,
      locale,
      profile,
      profileCompletionPending,
      setLocale,
      signIn,
      signOut,
      status,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used within AppProvider");
  return value;
}

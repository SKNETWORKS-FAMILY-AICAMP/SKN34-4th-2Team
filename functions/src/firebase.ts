import {getApps, getApp, initializeApp, type App} from "firebase-admin/app";
import {getAuth, type Auth} from "firebase-admin/auth";
import {
  FieldValue,
  Timestamp,
  getFirestore,
  type Firestore,
} from "firebase-admin/firestore";

/**
 * Discovery/deploy 타임아웃 방지용 lazy init.
 *
 * 주의: firebase-functions Gen2는 내부용 `__admin__` 앱을 미리 만들 수 있다.
 * getApps().length > 0 이어도 [DEFAULT] 앱이 없을 수 있으므로,
 * 이름/ getApp() 실패 여부로만 초기화한다.
 * @see https://github.com/firebase/firebase-functions/issues/689
 */
let _db: Firestore | undefined;
let _auth: Auth | undefined;
let _app: App | undefined;

function ensureApp(): App {
  if (_app) return _app;

  const existingDefault = getApps().find((a) => a.name === "[DEFAULT]");
  if (existingDefault) {
    _app = existingDefault;
    return _app;
  }

  try {
    _app = getApp();
  } catch {
    _app = initializeApp();
  }
  return _app;
}

/** 기존 모듈 호환 — admin.firestore.FieldValue / Timestamp */
export const admin = {
  firestore: {
    FieldValue,
    Timestamp,
  },
};

export const fieldValue = FieldValue;

export function ensureInitialized(): void {
  ensureApp();
}

export function getDb(): Firestore {
  if (!_db) {
    _db = getFirestore(ensureApp());
  }
  return _db;
}

export function getAuthAdmin(): Auth {
  if (!_auth) {
    _auth = getAuth(ensureApp());
  }
  return _auth;
}

/** Proxy — 기존 `db.collection(...)` 호출 유지 */
export const db: Firestore = new Proxy({} as Firestore, {
  get(_target, prop, receiver) {
    const instance = getDb();
    const value = Reflect.get(instance as object, prop, receiver);
    return typeof value === "function"
      ? (value as Function).bind(instance)
      : value;
  },
});

export const auth: Auth = new Proxy({} as Auth, {
  get(_target, prop, receiver) {
    const instance = getAuthAdmin();
    const value = Reflect.get(instance as object, prop, receiver);
    return typeof value === "function"
      ? (value as Function).bind(instance)
      : value;
  },
});

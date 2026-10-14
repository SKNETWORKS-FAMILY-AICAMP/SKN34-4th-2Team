import { useState } from 'react';

import type { AccountCredentials } from '../../data/repository';
import { Button, Dialog } from '../../ui/components';
import { Icon } from '../../ui/Icon';

/**
 * 계정 생성 · 비밀번호 재발급 결과 — credential_dialog.dart.
 * 비밀번호는 서버에 해시로만 남아 이 창을 닫으면 다시 볼 수 없다. 잃어버리면 재발급한다.
 */
export function CredentialDialog({
  title,
  credentials,
  onClose,
}: {
  title: string;
  credentials: AccountCredentials;
  onClose(): void;
}) {
  return (
    <Dialog title={title} onClose={onClose} actions={<Button onClick={onClose}>확인</Button>}>
      <CopyRow label="아이디 (이메일)" value={credentials.email} />
      <CopyRow label="비밀번호" value={credentials.password} />
      <p className="hint">
        이 창을 닫으면 비밀번호를 다시 볼 수 없습니다. 학생에게 전달한 뒤 닫아 주세요. 첫 로그인에서 비밀번호를 바꾸게 됩니다.
      </p>
    </Dialog>
  );
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="credential-row">
      <span className="hint">{label}</span>
      <code className="credential-row__value">{value}</code>
      <button type="button" className="icon-btn" aria-label={`${label} 복사`} onClick={copy}>
        <Icon name={copied ? 'check' : 'content_copy'} size={18} />
      </button>
    </div>
  );
}

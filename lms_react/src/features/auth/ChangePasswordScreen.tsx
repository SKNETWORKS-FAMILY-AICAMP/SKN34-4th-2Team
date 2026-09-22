import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { homeFor } from '../../app/routePaths';
import { Button, Card, Field, TextInput } from '../../ui/components';
import { useSession } from './session';

/** 첫 로그인 비밀번호 변경 — 지금 바꾸거나 나중에 마이페이지에서 바꾼다. */
export function ChangePasswordScreen() {
  const { user, changePassword, skipPasswordChange } = useSession();
  const navigate = useNavigate();
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const goHome = () => navigate(user === null ? '/' : homeFor(user.role), { replace: true });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 8) {
      setError('비밀번호는 8자 이상이어야 합니다.');
      return;
    }
    if (next !== confirm) {
      setError('두 번 입력한 비밀번호가 다릅니다.');
      return;
    }
    setSaving(true);
    void changePassword(next).then((result) => {
      if (!result.ok) {
        setError(result.message);
        setSaving(false);
        return;
      }
      goHome();
    });
  };

  const skip = () => {
    setSaving(true);
    void skipPasswordChange().then((result) => {
      if (!result.ok) {
        setError(result.message);
        setSaving(false);
        return;
      }
      goHome();
    });
  };

  return (
    <div className="centered-screen">
      <Card title="비밀번호 변경" className="centered-card">
        <p className="muted">첫 로그인입니다. 임시 비밀번호를 바꿔 주세요.</p>
        <form className="form-grid" onSubmit={submit}>
          <Field label="새 비밀번호" hint="8자 이상">
            <TextInput type="password" value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Field label="새 비밀번호 확인" error={error ?? undefined}>
            <TextInput type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <Button type="submit" disabled={saving}>
            {saving ? '처리 중' : '변경하고 시작하기'}
          </Button>
          <Button type="button" variant="outline" disabled={saving} onClick={skip}>
            나중에 변경하기
          </Button>
        </form>
      </Card>
    </div>
  );
}

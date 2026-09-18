import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { homeFor } from '../../app/routePaths';
import { Button, Card, Field, TextInput } from '../../ui/components';
import { useSession } from './session';

/** 비밀번호 변경 — features/auth/presentation/change_password_screen.dart */
export function ChangePasswordScreen() {
  const { user, changePassword } = useSession();
  const navigate = useNavigate();
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);

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
    changePassword(next);
    navigate(user === null ? '/' : homeFor(user.role), { replace: true });
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
          <Button type="submit">변경하고 시작하기</Button>
        </form>
      </Card>
    </div>
  );
}

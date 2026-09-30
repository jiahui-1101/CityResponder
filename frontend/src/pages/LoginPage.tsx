import { useState, type FormEvent } from "react";
import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ROLE_HOME_ROUTES } from "../navigation";
import { Button } from "../components/ui";

export function LoginPage() {
  const { login, authenticated, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (authenticated && user) return <Navigate to={ROLE_HOME_ROUTES[user.role]} replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true); setError(null);
    try { const user = await login(email, password); navigate(ROLE_HOME_ROUTES[user.role], { replace: true }); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Unable to sign in. Check your details and try again."); }
    finally { setSubmitting(false); }
  }

  return <main className="auth-page"><section className="login-card" aria-labelledby="login-title">
    <div className="login-brand"><div className="brand-mark" aria-hidden="true"><ShieldCheck size={22} /></div><div><strong>CityResponder</strong><span>Operational console</span></div></div>
    <div className="login-heading"><p className="eyebrow">Secure access</p><h1 id="login-title">Sign in to respond</h1><p>Use your CityResponder account to continue.</p></div>
    <form className="login-form" onSubmit={submit} noValidate>
      <label htmlFor="email">Email</label><input id="email" name="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
      <label htmlFor="password">Password</label><div className="password-field"><input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /><button className="password-toggle" type="button" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <Button type="submit" disabled={submitting}>{submitting ? "Signing in…" : "Sign in"}</Button>
    </form>
  </section></main>;
}

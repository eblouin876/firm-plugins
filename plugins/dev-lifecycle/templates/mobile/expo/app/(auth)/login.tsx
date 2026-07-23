/**
 * Login screen (public group). Collects email + password and calls
 * `auth.login`, which — on success — flips auth status to `authenticated`; the
 * (auth) group layout then redirects to the protected landing automatically.
 * On failure it surfaces a generic error (the backend deliberately returns an
 * indistinguishable 401 for unknown email vs wrong password).
 */
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "../../src/auth/useAuth";

export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = email.trim().length > 0 && password.length > 0 && !submitting;

  const onSubmit = async (): Promise<void> => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      // No navigation here — the (auth) layout redirects once status flips.
    } catch {
      setError("Incorrect email or password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <Text accessibilityRole="header" style={styles.title}>
          Sign in
        </Text>

        <Text style={styles.label} nativeID="email-label">
          Email
        </Text>
        <TextInput
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="username"
          accessibilityLabelledBy="email-label"
          accessibilityLabel="Email"
          editable={!submitting}
        />

        <Text style={styles.label} nativeID="password-label">
          Password
        </Text>
        <TextInput
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          textContentType="password"
          accessibilityLabelledBy="password-label"
          accessibilityLabel="Password"
          editable={!submitting}
        />

        {error != null ? (
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        ) : null}

        <Pressable
          style={[styles.button, !canSubmit && styles.buttonDisabled]}
          onPress={onSubmit}
          disabled={!canSubmit}
          accessibilityRole="button"
          accessibilityState={{ disabled: !canSubmit, busy: submitting }}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Sign in</Text>
          )}
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  container: { flex: 1, justifyContent: "center", padding: 24, gap: 8 },
  title: { fontSize: 28, fontWeight: "700", marginBottom: 16 },
  label: { fontSize: 14, fontWeight: "600", marginTop: 8 },
  input: {
    borderWidth: 1,
    borderColor: "#c7c7cc",
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
  },
  error: { color: "#c0392b", marginTop: 8 },
  button: {
    backgroundColor: "#0a7ea4",
    borderRadius: 8,
    padding: 16,
    alignItems: "center",
    marginTop: 16,
    minHeight: 52,
    justifyContent: "center",
  },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});

/**
 * Protected landing — the smallest end-to-end proof of bearer auth (the mobile
 * analog of the web's `/admin/ping` smoke). It calls the generated `/auth/me`
 * operation THROUGH the auth engine's `authorizedRequest`, so the request
 * carries `Authorization: Bearer <access>` and transparently refreshes + retries
 * on a 401. It renders the returned principal (id, email) plus the roles from
 * the access token's `roles` claim. No product screen — this exists to prove the
 * token reaches a protected endpoint and comes back.
 */
import { meAuthMeGet, type PrincipalOut } from "@repo/api-client";
import { useQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "../../src/auth/useAuth";

export default function LandingScreen() {
  const { roles, logout, authorizedRequest } = useAuth();

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () =>
      authorizedRequest<PrincipalOut>(async (init) => {
        const res = await meAuthMeGet(init);
        return res.status === 200 ? { status: 200, data: res.data } : { status: res.status };
      }),
  });

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text accessibilityRole="header" style={styles.title}>
          You&apos;re signed in
        </Text>

        {meQuery.isPending ? (
          <ActivityIndicator accessibilityLabel="Loading your profile" />
        ) : meQuery.data?.status === 200 && meQuery.data.data != null ? (
          <View style={styles.card}>
            <Row label="User ID" value={meQuery.data.data.id} />
            <Row label="Email" value={meQuery.data.data.email} />
            <Row label="Roles" value={roles.length > 0 ? roles.join(", ") : "(none)"} />
          </View>
        ) : (
          <Text style={styles.error} accessibilityRole="alert">
            Could not load your profile
            {meQuery.data != null ? ` (status ${meQuery.data.status})` : ""}.
          </Text>
        )}

        <Pressable
          style={styles.button}
          onPress={() => void logout()}
          accessibilityRole="button"
        >
          <Text style={styles.buttonText}>Sign out</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} selectable>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  container: { padding: 24, gap: 16 },
  title: { fontSize: 24, fontWeight: "700" },
  card: {
    borderWidth: 1,
    borderColor: "#e0e0e0",
    borderRadius: 12,
    padding: 16,
    gap: 12,
  },
  row: { gap: 2 },
  rowLabel: { fontSize: 12, fontWeight: "600", color: "#6b6b6b" },
  rowValue: { fontSize: 16 },
  error: { color: "#c0392b" },
  button: {
    backgroundColor: "#0a7ea4",
    borderRadius: 8,
    padding: 16,
    alignItems: "center",
    minHeight: 52,
    justifyContent: "center",
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});

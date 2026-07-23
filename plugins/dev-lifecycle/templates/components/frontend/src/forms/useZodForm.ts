import { useForm } from "react-hook-form";
import type { FieldValues, Resolver, UseFormProps, UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { ZodType } from "zod";

/**
 * `react-hook-form`'s `useForm` pre-wired with a zod resolver. Pass a zod
 * schema; the form's field types and validation both derive from it — one
 * source of truth. All other `useForm` options pass through (`defaultValues`,
 * `mode`, ...); only `resolver` is owned here.
 *
 * The resolver is cast to bridge zod's input/output types to RHF's generics —
 * a well-known, benign friction point between the two libraries' inference.
 */
export const useZodForm = <TOutput extends FieldValues, TInput extends FieldValues = TOutput>(
  schema: ZodType<TOutput, TInput>,
  options?: Omit<UseFormProps<TInput, unknown, TOutput>, "resolver">,
): UseFormReturn<TInput, unknown, TOutput> =>
  useForm<TInput, unknown, TOutput>({
    ...options,
    resolver: zodResolver(schema) as Resolver<TInput, unknown, TOutput>,
  });

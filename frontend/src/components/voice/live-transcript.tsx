import { useEffect } from "react";
import { AnimatePresence, motion } from "motion/react";
import { componentTransition } from "@/lib/motion";
import { useVoiceTranscriptStore } from "@/stores/voice-transcript.store";

/** How long the transcript stays visible after the last word arrives,
 *  before fading -- "Fade after conversation" per the voice experience
 *  brief. Not a design token (`styles/tokens.css`'s three motion tiers
 *  are for transition durations, not this kind of idle timeout), so it
 *  lives here as the one place this specific behavior is defined. */
const FADE_AFTER_INACTIVITY_MS = 4000;

/**
 * Streaming word-by-word transcript, rendered below `VoiceString`
 * (Phase 4, Task Group H). Purely a view over `useVoiceTranscriptStore`
 * -- starts and stays empty (renders nothing) until a real speech-to-
 * text stream actually appends words; never seeded with placeholder
 * text.
 */
export function LiveTranscript() {
  const words = useVoiceTranscriptStore((s) => s.words);
  const clear = useVoiceTranscriptStore((s) => s.clear);

  useEffect(() => {
    if (words.length === 0) return;
    const timeout = setTimeout(clear, FADE_AFTER_INACTIVITY_MS);
    return () => clearTimeout(timeout);
  }, [words, clear]);

  if (words.length === 0) return null;

  return (
    <p aria-live="polite" className="flex max-w-md flex-wrap justify-center gap-x-1.5 text-body text-foreground">
      <AnimatePresence initial={false}>
        {words.map((word) => (
          <motion.span
            key={word.id}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={componentTransition}
          >
            {word.text}
          </motion.span>
        ))}
      </AnimatePresence>
    </p>
  );
}

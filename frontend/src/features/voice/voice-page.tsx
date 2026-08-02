import { LiveTranscript } from "@/components/voice/live-transcript";
import { VoiceString } from "@/components/voice/voice-string";

/**
 * The Voice module's real route element (Phase 4, Task Group H) --
 * replaces `routes/placeholder-route.tsx`'s generic screen for `voice`
 * specifically. Pure composition: `VoiceString` is JARVIS's voice
 * identity (state communicated through the wave itself, never a text
 * label); `LiveTranscript` renders beneath it and disappears entirely
 * when there's nothing real to show.
 */
export function VoicePage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6">
      <VoiceString />
      <LiveTranscript />
    </div>
  );
}

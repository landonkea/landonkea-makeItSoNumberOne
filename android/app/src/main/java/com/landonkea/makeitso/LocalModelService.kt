// ───────────────────────────────────────────────────────────────────
// LocalModelService.kt, genuine on-device LLM inference (Android)
// ───────────────────────────────────────────────────────────────────
// This is Android's real equivalent of desktop's Ollama support (see
// desktop/core/ai.py's process_with_ollama()/list_ollama_models()):
// it runs a small language model ENTIRELY ON THE PHONE, no network
// call, no server to keep running.
//
// WHAT IT USES: Google's MediaPipe LLM Inference API
// (com.google.mediapipe:tasks-genai, see app/build.gradle.kts), the
// officially supported way to run an LLM on-device on Android. It
// loads a quantized Gemma model bundled as a single ".task" file and
// runs inference locally via LiteRT (Google's on-device ML runtime).
//
// WHY THIS REPLACED THE OLD "OFFLINE" PATH: the previous version of
// ClaudeService.kt called http://localhost:11434 (Ollama's API), but
// on a phone, "localhost" means the phone itself. There is no Ollama
// server running on the phone, so that call could never succeed on a
// real device; it only ever worked in a very specific dev setup
// (Android emulator + adb reverse tunnel to a laptop running Ollama).
// That's a dev convenience, not real offline/local support. This file
// replaces it with inference that actually runs on the device.
//
// WHY THE MODEL ISN'T AUTO-DOWNLOADED (unlike desktop's Ollama, which
// CAN auto-pull): Ollama's models are hosted by Ollama itself with no
// login required, so desktop's ollama_auto_pull works with a plain
// HTTP call. MediaPipe's supported Gemma models are hosted on Hugging
// Face behind Google's Gemma license, downloading one requires the
// user to sign in and accept that license in a browser first. There
// is no anonymous API to fetch it programmatically. So, like desktop
// tells the user to run `ollama pull llama3.2` themselves, this file
// tells the user to download the .task file themselves, see
// printMissingModelHelp() below. This is the honest constraint, not a
// missing feature.
// ───────────────────────────────────────────────────────────────────

package com.landonkea.makeitso

import android.content.Context
import com.google.mediapipe.tasks.genai.llminference.LlmInference
import com.google.mediapipe.tasks.genai.llminference.LlmInference.LlmInferenceOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

// "object" makes this a singleton, mirroring ClaudeService, one LlmInference engine (once
// created) is reused for the app's lifetime rather than reloading the model file on every call,
// which would be slow (model loading takes real time, unlike a network round-trip).
object LocalModelService {

    // ── Where the model file lives on disk ───────────────────────
    // getExternalFilesDir(null) is app-private storage that's still reachable via `adb push`
    // without needing root, the standard place to hand a large file to an Android app during
    // development. Falls back to internal filesDir if external storage isn't mounted (e.g. no
    // SD card / USB storage state), matching how MediaPipe's own sample app resolves this path.
    private const val MODEL_FILENAME = "gemma3-1b-it-int4.task"

    private fun modelFile(context: Context): File {
        val dir = context.getExternalFilesDir(null) ?: context.filesDir
        return File(dir, MODEL_FILENAME)
    }

    // ── The loaded inference engine (created once, lazily) ───────
    // "@Volatile" ensures a value written on one thread is visible to another immediately,
    // relevant here because generateResponse() below can be called from different coroutine
    // dispatchers over the app's lifetime, all reading/writing this same cached reference.
    @Volatile
    private var engine: LlmInference? = null

    // ── Public check: is a local model actually available? ───────
    // ClaudeService calls this before attempting inference, so it can decide whether to print
    // the "how to install" help (see below) instead of trying and failing. Mirrors desktop's
    // _is_ollama_running() playing the same role for the Ollama path.
    fun isModelAvailable(context: Context): Boolean {
        return modelFile(context).exists()
    }

    // ── Run one inference call against the local model ───────────
    // Returns the raw generated text, or null if the model file is missing or inference throws
    // (out-of-memory on very low-RAM devices is a real, expected failure mode for on-device LLM
    // inference, we catch it rather than crash the whole app). Runs on Dispatchers.Default
    // (CPU-bound work), not Dispatchers.IO, this is compute, not I/O, once the model is loaded.
    suspend fun generateResponse(context: Context, prompt: String): String? {
        if (!isModelAvailable(context)) {
            printMissingModelHelp()
            return null
        }
        return withContext(Dispatchers.Default) {
            try {
                val llm = engine ?: createEngine(context).also { engine = it }
                // generateResponse() is MediaPipe's synchronous, blocking call, it returns only
                // once the full response has been generated. We deliberately don't use the
                // *Async variant (which streams partial tokens via a callback) because
                // ClaudeService's shared response-parsing path (buildResultFromResponse's Ollama/
                // Claude equivalent) expects one complete string, matching how the Claude and
                // (previously) Ollama providers both behave in this file already.
                llm.generateResponse(prompt)
            } catch (e: Exception) {
                // Common real failure here: OutOfMemoryError-adjacent native allocation failures
                // on devices with too little RAM for even a 1B-parameter model, or a corrupted/
                // partial .task file from an interrupted adb push. Either way, fail soft.
                e.printStackTrace()
                // Drop a possibly-broken engine so the NEXT call retries creation from scratch
                // instead of repeatedly reusing something that failed once.
                engine = null
                null
            }
        }
    }

    // ── Build the LlmInference engine from the on-disk model file ─
    // Separated into its own function so generateResponse() above stays focused on the
    // call-and-handle-errors flow. maxTokens/topK/temperature mirror the values already used for
    // Ollama's "options" block elsewhere in this codebase (see ClaudeService.kt's num_predict:
    // 512), kept the same so local-model responses aren't noticeably shorter/more random than
    // the cloud or (previously) Ollama ones.
    private fun createEngine(context: Context): LlmInference {
        val options = LlmInferenceOptions.builder()
            .setModelPath(modelFile(context).absolutePath)
            .setMaxTokens(512)
            .setMaxTopK(40)
            .build()
        return LlmInference.createFromOptions(context, options)
    }

    // ── Release native resources ──────────────────────────────────
    // MediaPipe's LlmInference holds native (C++) memory for the loaded model weights, this
    // must be explicitly closed or that memory leaks for the life of the process. Call this from
    // MainActivity.onDestroy() alongside the existing wakeWordDetector/tts cleanup, but only if
    // an engine was actually created (mirrors the wakeWordDetectorLazy.isInitialized() pattern
    // already used there, no point creating an engine just to immediately destroy it).
    fun close() {
        engine?.close()
        engine = null
    }

    // ── Print setup instructions when the model file isn't present ─
    // Mirrors desktop's _print_ollama_missing_help() in spirit: tell the user exactly what to
    // download and how to get it onto the device, since, unlike Ollama, there's no
    // auto-download path available here (see the file header comment for why).
    private fun printMissingModelHelp() {
        println("  ╔══════════════════════════════════════════════════╗")
        println("  ║  No local model found!                            ║")
        println("  ║                                                    ║")
        println("  ║  To enable on-device offline mode:                ║")
        println("  ║  1. On a computer, sign in to huggingface.co and  ║")
        println("  ║     accept the Gemma license, then download:      ║")
        println("  ║     litert-community/Gemma3-1B-IT                 ║")
        println("  ║     (file: $MODEL_FILENAME)")
        println("  ║  2. With the phone connected via USB (adb):       ║")
        println("  ║     adb push $MODEL_FILENAME \\")
        println("  ║       /sdcard/Android/data/com.landonkea.makeitso/")
        println("  ║       files/$MODEL_FILENAME")
        println("  ║  3. Restart the app.                              ║")
        println("  ╚══════════════════════════════════════════════════╝")
    }
}
// End of LocalModelService.

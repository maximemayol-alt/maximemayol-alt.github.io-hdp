#!/usr/bin/env node
/**
 * Next Scorer Bot — Basketball next-scorer prediction CLI
 * Uses Claude claude-sonnet-4-6 with prompt caching for the stable system prompt.
 *
 * Usage: ANTHROPIC_API_KEY=<key> node bot.js
 */

import Anthropic from '@anthropic-ai/sdk';
import readline from 'readline';

const client = new Anthropic();

// Stable system prompt — cached via cache_control so repeated turns don't re-bill it
const SYSTEM_PROMPT = `You are an elite basketball analyst specializing in live-game next-scorer prediction.

Your role is to analyze the current game state and identify which player is most likely to score next, explaining your reasoning with statistical and situational factors.

## What you analyze

**Offensive factors:**
- Ball handler and shot creator on the current possession
- Isolation, pick-and-roll, or off-ball movement tendencies
- Hot hand: players who have scored recently or are "in rhythm"
- Usage rate and shot volume for each player
- Field-goal percentage from different zones

**Defensive matchups:**
- Mismatches being exploited (size, speed, fatigue)
- Defensive rotations and help-side gaps
- Foul trouble on defenders (they play softer = easier to score)

**Game context:**
- Score differential: trailing teams look for specific scorers to cut deficits
- Time remaining: late-clock urgency pushes ball to the best isolator
- Timeout just called: set plays often target a specific player
- Player fatigue and minutes played
- Momentum swings after turnovers or big plays

**Output format:**
For each prediction, provide:
1. **Most likely next scorer** — name and jersey number if known
2. **Probability estimate** — rough % (e.g. "~35%")
3. **Top 2–3 alternatives** — other candidates with brief reasoning
4. **Key reasoning** — 2–4 bullet points explaining WHY this player is most likely
5. **Watch for** — one situational trigger that could change the prediction

If the user provides player stats, use them. If they don't, work from the narrative context they give you.

Keep responses concise and directly actionable. Use basketball terminology naturally.`;

const conversationHistory = [];

/**
 * Send a message to Claude and return the assistant reply.
 * The system prompt is cached (cache_control: ephemeral) so it is only
 * billed at full rate on the first call; subsequent turns read from cache.
 */
async function chat(userMessage) {
  conversationHistory.push({ role: 'user', content: userMessage });

  const response = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1024,
    system: [
      {
        type: 'text',
        text: SYSTEM_PROMPT,
        cache_control: { type: 'ephemeral' },
      },
    ],
    messages: conversationHistory,
  });

  const assistantText = response.content.find((b) => b.type === 'text')?.text ?? '';
  conversationHistory.push({ role: 'assistant', content: assistantText });

  // Log cache stats in debug mode
  if (process.env.DEBUG) {
    const u = response.usage;
    console.error(
      `[tokens] input=${u.input_tokens} cached_read=${u.cache_read_input_tokens ?? 0}` +
        ` cached_write=${u.cache_creation_input_tokens ?? 0} output=${u.output_tokens}`,
    );
  }

  return assistantText;
}

/** Print the welcome banner and usage hint. */
function printBanner() {
  console.log('');
  console.log('╔══════════════════════════════════════════════════════╗');
  console.log('║         NEXT SCORER BOT  🏀  (powered by Claude)    ║');
  console.log('╠══════════════════════════════════════════════════════╣');
  console.log('║  Describe the current game state and get a next-     ║');
  console.log('║  scorer prediction with reasoning.                   ║');
  console.log('║                                                      ║');
  console.log('║  Examples:                                           ║');
  console.log('║  • "Lakers up 3 with 45s left, LeBron has the ball" ║');
  console.log('║  • "Curry 8/15 FG, defender in foul trouble"        ║');
  console.log('║  • "reset" — clear conversation history             ║');
  console.log('║  • "quit" or Ctrl-C — exit                          ║');
  console.log('╚══════════════════════════════════════════════════════╝');
  console.log('');
}

/** Main interactive loop. */
async function main() {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error('Error: ANTHROPIC_API_KEY environment variable is not set.');
    console.error('Export it before running: export ANTHROPIC_API_KEY=<your-key>');
    process.exit(1);
  }

  printBanner();

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: process.stdin.isTTY,
  });

  // Graceful Ctrl-C
  rl.on('SIGINT', () => {
    console.log('\nGoodbye! 🏀');
    process.exit(0);
  });

  const prompt = () =>
    new Promise((resolve) => rl.question('You › ', resolve));

  while (true) {
    let input;
    try {
      input = await prompt();
    } catch {
      // readline closed (pipe end / EOF)
      break;
    }

    input = input.trim();
    if (!input) continue;

    if (input.toLowerCase() === 'quit' || input.toLowerCase() === 'exit') {
      console.log('Goodbye! 🏀');
      rl.close();
      break;
    }

    if (input.toLowerCase() === 'reset') {
      conversationHistory.length = 0;
      console.log('\n[Conversation history cleared.]\n');
      continue;
    }

    try {
      process.stdout.write('\nBot › ');
      const reply = await chat(input);
      console.log(reply);
      console.log('');
    } catch (err) {
      if (err instanceof Anthropic.APIError) {
        console.error(`\nAPI error (${err.status}): ${err.message}\n`);
      } else {
        console.error('\nUnexpected error:', err.message, '\n');
      }
    }
  }
}

main();

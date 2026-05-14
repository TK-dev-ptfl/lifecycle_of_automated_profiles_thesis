import { useState, useEffect } from 'react'

import { useQuery } from '@tanstack/react-query'
import { getBots, updateBot } from '../../api/bots'
import { createEmail, getEmailPlatforms } from '../../api/emails'
import { Button } from '../../components/ui/Button'
import type { Bot } from '../../types'

function saveProgress(p: ProgressMap) { localStorage.setItem('pipeline_progress_v2', JSON.stringify(p)) }

async function syncBotPipelineState(botId: string, inPipeline: boolean) {
  try {
    if (inPipeline) {
      await updateBot(botId, { state: 'in_pipeline', status: 'running' } as Partial<Bot>)
      return
    }
    await updateBot(botId, { state: 'not_active', status: 'stopped' } as Partial<Bot>)
  } catch {
    // Keep UI flow working even if state sync fails.
  }
}

// ─── Data model ───────────────────────────────────────────────────────────────

interface ManualInput {
  key: string
  label: string
  type: 'text' | 'email' | 'password' | 'textarea' | 'confirm'
  placeholder?: string
}

interface PipelineStep {
  id: string
  title: string
  description: string
  type: 'auto' | 'manual'
  algorithmId?: string
  instructions?: string
  inputs?: ManualInput[]
}

interface Pipeline {
  id: string
  platform: string
  pipelineType: 'creation' | 'trust'
  emailProvider?: string
  title: string
  description: string
  steps: PipelineStep[]
}

interface EmailProviderDef {
  id: string
  type: 'temporary' | 'own_mailserver' | 'classic'
  name: string
  domain: string
}

// ─── Reddit pipelines only ────────────────────────────────────────────────────

const PIPELINES: Pipeline[] = [
  {
    id: 'rd-creation',
    platform: 'reddit',
    pipelineType: 'creation',
    title: 'Reddit Account Creation',
    description: 'Fully automated Reddit account creation workflow.',
    steps: [
      {
        id: 'get-proxy',
        title: 'Allocate Proxy',
        description: 'Get an unassigned proxy that is not flagged by Reddit.',
        type: 'manual',
        instructions: 'System will assign a proxy. Verify it is available in your proxy pool.',
        inputs: [
          { key: 'proxy_confirmed', label: 'Proxy assigned?', type: 'confirm' },
        ],
      },
      {
        id: 'get-email',
        title: 'Allocate Email',
        description: 'Get an unassigned email account from the email pool.',
        type: 'manual',
        instructions: 'System will assign an email. Confirm it is available.',
        inputs: [
          { key: 'email_confirmed', label: 'Email allocated?', type: 'confirm' },
        ],
      },
      {
        id: 'get-identity',
        title: 'Generate Identity',
        description: 'Get or generate identity information for the account.',
        type: 'manual',
        instructions: 'System will prepare identity data. Confirm it is ready.',
        inputs: [
          { key: 'identity_confirmed', label: 'Identity ready?', type: 'confirm' },
        ],
      },
      {
        id: 'navigate-reddit',
        title: 'Navigate to Reddit',
        description: 'Open https://www.reddit.com/ in browser.',
        type: 'manual',
        instructions: 'Go to https://www.reddit.com/ and verify page loaded.',
        inputs: [
          { key: 'page_ready', label: 'Reddit homepage loaded?', type: 'confirm' },
        ],
      },
      {
        id: 'click-signin',
        title: 'Click Sign In',
        description: 'Click the Sign In button.',
        type: 'manual',
        instructions: 'Click the "Sign in" button on the Reddit homepage.',
        inputs: [
          { key: 'signin_clicked', label: 'Sign in page visible?', type: 'confirm' },
        ],
      },
      {
        id: 'scroll-register',
        title: 'Scroll Down',
        description: 'Scroll down to find the Register link.',
        type: 'manual',
        instructions: 'Scroll down on the sign in page.',
        inputs: [
          { key: 'register_visible', label: 'Register link visible?', type: 'confirm' },
        ],
      },
      {
        id: 'click-register',
        title: 'Click Register',
        description: 'Click the link to register a new account.',
        type: 'manual',
        instructions: 'Click the "Sign up" or register link.',
        inputs: [
          { key: 'register_page_open', label: 'Registration form loaded?', type: 'confirm' },
        ],
      },
      {
        id: 'fill-email',
        title: 'Enter Email',
        description: 'Fill in email field with allocated email.',
        type: 'manual',
        instructions: 'Enter the allocated email address and click Continue.',
        inputs: [
          { key: 'email_submitted', label: 'Email submitted?', type: 'confirm' },
        ],
      },
      {
        id: 'get-verify-code',
        title: 'Get Verification Code',
        description: 'Retrieve verification code from email inbox.',
        type: 'manual',
        instructions: 'Check the allocated email inbox for the verification code sent by Reddit.',
        inputs: [
          { key: 'code_retrieved', label: 'Code retrieved?', type: 'text', placeholder: '000000' },
        ],
      },
      {
        id: 'enter-verify-code',
        title: 'Enter Verification Code',
        description: 'Enter the code received from email.',
        type: 'manual',
        instructions: 'Enter the verification code on Reddit and click Continue.',
        inputs: [
          { key: 'code_verified', label: 'Code entered and accepted?', type: 'confirm' },
        ],
      },
      {
        id: 'change-username',
        title: 'Set Username',
        description: 'Choose or confirm username (optional, can keep auto-generated).',
        type: 'manual',
        instructions: 'Change username if desired, or keep the suggested username. Click Continue.',
        inputs: [
          { key: 'username', label: 'Username set?', type: 'text', placeholder: 'throwaway_user_1234' },
        ],
      },
      {
        id: 'enter-password',
        title: 'Set Password',
        description: 'Enter password for the account.',
        type: 'manual',
        instructions: 'Enter a strong password and click Continue.',
        inputs: [
          { key: 'password_set', label: 'Password entered?', type: 'confirm' },
        ],
      },
      {
        id: 'enter-gender',
        title: 'Gender Preference',
        description: 'Select gender (optional, can skip).',
        type: 'manual',
        instructions: 'Optionally select gender preference or skip this step.',
        inputs: [
          { key: 'gender_completed', label: 'Step completed?', type: 'confirm' },
        ],
      },
      {
        id: 'enter-interests',
        title: 'Select Interests',
        description: 'Choose content interests (optional, can skip).',
        type: 'manual',
        instructions: 'Optionally select interests matching bot\'s focus, or skip this step.',
        inputs: [
          { key: 'interests_completed', label: 'Step completed?', type: 'confirm' },
        ],
      },
      {
        id: 'content-personalization',
        title: 'Content Personalization',
        description: 'Customize content preferences (optional, can skip).',
        type: 'manual',
        instructions: 'Optionally configure content personalization or skip this step.',
        inputs: [
          { key: 'personalization_completed', label: 'Step completed?', type: 'confirm' },
        ],
      },
      {
        id: 'activity-simulation',
        title: 'Simulate Activity',
        description: 'Scroll content and simulate activity before finishing.',
        type: 'manual',
        instructions: 'Scroll through the feed for a while to simulate real activity. You can repeat this step multiple times.',
        inputs: [
          { key: 'activity_simulated', label: 'Activity simulated?', type: 'confirm' },
        ],
      },
      {
        id: 'enter-sandbox',
        title: 'Finalize Account',
        description: 'Complete account creation and enter sandbox environment.',
        type: 'manual',
        instructions: 'Verify account is fully created and ready. Click to continue.',
        inputs: [
          { key: 'account_complete', label: 'Account creation complete?', type: 'confirm' },
        ],
      },
    ],
  },
  {
    id: 'rd-trust',
    platform: 'reddit',
    pipelineType: 'trust',
    title: 'Reddit Trust Building',
    description: 'Builds account karma and age for operational credibility.',
    steps: [
      {
        id: 'day-1',
        title: 'Deň 1 — Čítanie',
        description: 'Len scrollovanie, žiadne akcie.',
        type: 'manual',
        instructions: 'Prihlásiť sa, počkať 45s. Scrollovať r/popular a r/all, otvoriť 3–5 príspevkov. Relácia 10–15 min. Max akcie: 0.',
        inputs: [
          { key: 'day1_complete', label: 'Deň 1 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-2',
        title: 'Deň 2 — Prvé upvoty',
        description: 'Scrollovanie + max 3 upvoty príspevkov.',
        type: 'manual',
        instructions: 'Scrollovať r/popular a záujmové subreddity. Relácia 10–15 min. Max upvoty príspevkov: 3. Max komentáre: 0. Max príspevky: 0.',
        inputs: [
          { key: 'day2_upvotes', label: 'Počet upvotov', type: 'text', placeholder: '0' },
          { key: 'day2_complete', label: 'Deň 2 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-3',
        title: 'Deň 3 — Upvoty príspevkov aj komentárov',
        description: 'Max 5 upvotov príspevkov, max 2 upvoty komentárov.',
        type: 'manual',
        instructions: 'Scrollovať záujmové subreddity. Relácia 10–20 min. Max upvoty príspevkov: 5. Max upvoty komentárov: 2. Max komentáre: 0. Max príspevky: 0.',
        inputs: [
          { key: 'day3_post_upvotes', label: 'Upvoty príspevkov', type: 'text', placeholder: '0' },
          { key: 'day3_comment_upvotes', label: 'Upvoty komentárov', type: 'text', placeholder: '0' },
          { key: 'day3_complete', label: 'Deň 3 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-4',
        title: 'Deň 4 — Prvý komentár',
        description: 'Max 1 komentár, min 4 slová, nekontroverznú tému.',
        type: 'manual',
        instructions: 'Scrollovať, upvotovať. Relácia 15–20 min. Max upvoty príspevkov: 5. Max upvoty komentárov: 3. Max komentáre: 1. Delay medzi akciami: 8s ± 3s.',
        inputs: [
          { key: 'day4_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day4_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day4_complete', label: 'Deň 4 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-5',
        title: 'Deň 5 — Viac komentárov',
        description: 'Max 2 komentáre v rôznych subredditoch, min 6 slov.',
        type: 'manual',
        instructions: 'Scrollovať, upvotovať. Relácia 15–20 min. Max upvoty príspevkov: 6. Max upvoty komentárov: 4. Max komentáre: 2. Delay: 8s ± 3s.',
        inputs: [
          { key: 'day5_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day5_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day5_complete', label: 'Deň 5 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-6',
        title: 'Deň 6 — Subscribe + komentáre',
        description: 'Subscribe do 3–5 záujmových subredditov, max 3 komentáre.',
        type: 'manual',
        instructions: 'Scrollovať, upvotovať. Relácia 15–20 min. Max upvoty príspevkov: 7. Max upvoty komentárov: 4. Max komentáre: 3. Max subscribe: 5. Delay: 7s ± 3s.',
        inputs: [
          { key: 'day6_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day6_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day6_subscribes', label: 'Počet subscribe', type: 'text', placeholder: '0' },
          { key: 'day6_complete', label: 'Deň 6 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-7',
        title: 'Deň 7 — Odpovede na komentáre',
        description: 'Max 4 komentáre vrátane 1 odpovede na iný komentár.',
        type: 'manual',
        instructions: 'Scrollovať, upvotovať. Relácia 15–25 min. Max upvoty príspevkov: 8. Max upvoty komentárov: 5. Max komentáre: 4 (vrátane 1 reply). Delay: 7s ± 3s.',
        inputs: [
          { key: 'day7_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day7_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day7_complete', label: 'Deň 7 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-8',
        title: 'Deň 8 — Prvý príspevok',
        description: 'Prvý vlastný príspevok v sandbox subreddite.',
        type: 'manual',
        instructions: 'Scrollovať, upvotovať. Relácia 20–25 min. Max upvoty príspevkov: 8. Max upvoty komentárov: 5. Max komentáre: 3. Max príspevky: 1 (jednoduchá otázka alebo neutrálny link). Delay: 6s ± 3s.',
        inputs: [
          { key: 'day8_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day8_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day8_posts', label: 'Počet príspevkov', type: 'text', placeholder: '0' },
          { key: 'day8_complete', label: 'Deň 8 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-9',
        title: 'Deň 9 — Reakcie na vlastný príspevok',
        description: 'Reagovať na odpovede pod príspevkom z dňa 8.',
        type: 'manual',
        instructions: 'Scrollovať, upvotovať. Relácia 20–25 min. Max upvoty príspevkov: 9. Max upvoty komentárov: 6. Max komentáre: 4. Max príspevky: 1. Delay: 6s ± 3s.',
        inputs: [
          { key: 'day9_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day9_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day9_complete', label: 'Deň 9 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-10',
        title: 'Deň 10 — Plná aktivita',
        description: 'Max 10 upvotov príspevkov, 6 komentárov, 1 príspevok.',
        type: 'manual',
        instructions: 'Scrollovať, upvotovať. Relácia 20–25 min. Max upvoty príspevkov: 10. Max upvoty komentárov: 6. Max komentáre: 5. Max príspevky: 1. Delay: 6s ± 3s.',
        inputs: [
          { key: 'day10_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day10_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day10_posts', label: 'Počet príspevkov', type: 'text', placeholder: '0' },
          { key: 'day10_complete', label: 'Deň 10 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-11',
        title: 'Deň 11 — Kontrola karmy',
        description: 'Bežná aktivita + overenie karma skóre (min +5).',
        type: 'manual',
        instructions: 'Relácia 20–25 min. Max upvoty príspevkov: 10. Max upvoty komentárov: 7. Max komentáre: 5. Max príspevky: 1. Delay: 5s ± 3s. Skontrolovať karma — očakávaný min. +5.',
        inputs: [
          { key: 'day11_link_karma', label: 'Link karma', type: 'text', placeholder: '0' },
          { key: 'day11_comment_karma', label: 'Comment karma', type: 'text', placeholder: '0' },
          { key: 'day11_complete', label: 'Deň 11 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-12',
        title: 'Deň 12 — Follow používateľov',
        description: 'Max 2 príspevky, follow max 3 používateľov.',
        type: 'manual',
        instructions: 'Relácia 20–25 min. Max upvoty príspevkov: 11. Max upvoty komentárov: 7. Max komentáre: 5. Max príspevky: 2. Max follow: 3. Delay: 5s ± 3s.',
        inputs: [
          { key: 'day12_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day12_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day12_follows', label: 'Počet follow', type: 'text', placeholder: '0' },
          { key: 'day12_complete', label: 'Deň 12 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-13',
        title: 'Deň 13 — Reakcie na vlastné príspevky',
        description: 'Odpovedať na komentáre pod vlastnými príspevkami.',
        type: 'manual',
        instructions: 'Relácia 20–25 min. Max upvoty príspevkov: 12. Max upvoty komentárov: 8. Max komentáre: 6. Max príspevky: 2. Delay: 5s ± 3s.',
        inputs: [
          { key: 'day13_upvotes', label: 'Celkom upvotov', type: 'text', placeholder: '0' },
          { key: 'day13_comments', label: 'Počet komentárov', type: 'text', placeholder: '0' },
          { key: 'day13_complete', label: 'Deň 13 dokončený?', type: 'confirm' },
        ],
      },
      {
        id: 'day-14',
        title: 'Deň 14 — Verifikácia účtu',
        description: 'Shadowban check + Botometer skóre + finálna kontrola karmy.',
        type: 'manual',
        instructions: 'Relácia 20–30 min. Max upvoty príspevkov: 12. Max upvoty komentárov: 8. Max komentáre: 6. Max príspevky: 2. Delay: 5s ± 3s. Skontrolovať shadowban z kontrolného účtu. Botometer skóre — očakávaný max 0.3.',
        inputs: [
          { key: 'link_karma', label: 'Link karma', type: 'text', placeholder: '0' },
          { key: 'comment_karma', label: 'Comment karma', type: 'text', placeholder: '0' },
          { key: 'account_age_days', label: 'Vek účtu (dni)', type: 'text', placeholder: '0' },
          { key: 'botometer_score', label: 'Botometer skóre', type: 'text', placeholder: '0.0' },
          { key: 'shadowban_clear', label: 'Shadowban check OK?', type: 'confirm' },
          { key: 'warmup_complete', label: 'Warm-up dokončený?', type: 'confirm' },
        ],
      },
    ],
  },
]

// ─── Email pipelines ──────────────────────────────────────────────────────────

const EMAIL_PIPELINES: Pipeline[] = [
  {
    id: 'email-creation',
    platform: 'email',
    pipelineType: 'creation',
    emailProvider: 'tuta',
    title: 'Email Account Creation (Tuta)',
    description: 'Manual Tuta signup workflow.',
    steps: [
      {
        id: 'open-signup',
        title: 'Open Tuta Signup',
        description: 'Open the Tuta signup page.',
        type: 'manual',
        instructions: 'Go to https://app.tuta.com/signup',
        inputs: [
          { key: 'signup_opened', label: 'Signup page opened?', type: 'confirm' },
        ],
      },
      {
        id: 'click-free',
        title: 'Click Free',
        description: 'Select the free plan.',
        type: 'manual',
        instructions: 'Click "Free".',
        inputs: [
          { key: 'free_clicked', label: 'Free selected?', type: 'confirm' },
        ],
      },
      {
        id: 'continue-1',
        title: 'Continue',
        description: 'Proceed to account form.',
        type: 'manual',
        instructions: 'Click Continue.',
        inputs: [
          { key: 'continued_1', label: 'Continued?', type: 'confirm' },
        ],
      },
      {
        id: 'enter-username',
        title: 'Enter Username',
        description: 'Fill in desired username.',
        type: 'manual',
        instructions: 'Enter username.',
        inputs: [
          { key: 'username_entered', label: 'Username entered?', type: 'confirm' },
        ],
      },
      {
        id: 'enter-password',
        title: 'Enter Password',
        description: 'Set password.',
        type: 'manual',
        instructions: 'Enter password.',
        inputs: [
          { key: 'password_entered', label: 'Password entered?', type: 'confirm' },
        ],
      },
      {
        id: 'repeat-password',
        title: 'Repeat Password',
        description: 'Confirm password.',
        type: 'manual',
        instructions: 'Repeat password.',
        inputs: [
          { key: 'password_repeated', label: 'Password repeated?', type: 'confirm' },
        ],
      },
      {
        id: 'check-boxes',
        title: 'Check Boxes',
        description: 'Accept required checkboxes.',
        type: 'manual',
        instructions: 'Check all required boxes.',
        inputs: [
          { key: 'boxes_checked', label: 'Required boxes checked?', type: 'confirm' },
        ],
      },
      {
        id: 'create-account',
        title: 'Click Create Account',
        description: 'Submit account creation form.',
        type: 'manual',
        instructions: 'Click Create Account.',
        inputs: [
          { key: 'create_clicked', label: 'Create account clicked?', type: 'confirm' },
        ],
      },
      {
        id: 'captcha',
        title: 'Captcha',
        description: 'Complete captcha challenge.',
        type: 'manual',
        instructions: 'Solve captcha.',
        inputs: [
          { key: 'captcha_done', label: 'Captcha completed?', type: 'confirm' },
        ],
      },
      {
        id: 'post-captcha-checkbox',
        title: 'Check Box',
        description: 'Complete additional checkbox step.',
        type: 'manual',
        instructions: 'Check the checkbox.',
        inputs: [
          { key: 'post_captcha_checkbox_done', label: 'Checkbox checked?', type: 'confirm' },
        ],
      },
      {
        id: 'continue-2',
        title: 'Continue',
        description: 'Proceed after captcha/checkbox.',
        type: 'manual',
        instructions: 'Click Continue.',
        inputs: [
          { key: 'continued_2', label: 'Continued?', type: 'confirm' },
        ],
      },
      {
        id: 'wait-auto-approval-click',
        title: 'Click Wait For Auto Approval',
        description: 'Trigger auto-approval wait state.',
        type: 'manual',
        instructions: 'Click "Wait for auto approval".',
        inputs: [
          { key: 'wait_auto_approval_clicked', label: 'Clicked wait for auto approval?', type: 'confirm' },
        ],
      },
      {
        id: 'wait-48-hours',
        title: 'Wait 48 Hours',
        description: 'Wait for approval window.',
        type: 'manual',
        instructions: 'Wait 48 hours.',
        inputs: [
          { key: 'wait_48h_complete', label: '48 hours completed?', type: 'confirm' },
        ],
      },
    ],
  },
  {
    id: 'email-verification-tuta',
    platform: 'email',
    pipelineType: 'trust',
    emailProvider: 'tuta',
    title: 'Email Verification (Tuta)',
    description: 'Manual Tuta login and code retrieval workflow.',
    steps: [
      {
        id: 'open-login',
        title: 'Open Tuta Login',
        description: 'Open Tuta login page.',
        type: 'manual',
        instructions: 'Go to https://app.tuta.com/login',
        inputs: [
          { key: 'login_opened', label: 'Login page opened?', type: 'confirm' },
        ],
      },
      {
        id: 'enter-email',
        title: 'Enter Email',
        description: 'Fill in email address.',
        type: 'manual',
        instructions: 'Enter email.',
        inputs: [
          { key: 'email_entered', label: 'Email entered?', type: 'confirm' },
        ],
      },
      {
        id: 'enter-password',
        title: 'Enter Password',
        description: 'Fill in password.',
        type: 'manual',
        instructions: 'Enter password.',
        inputs: [
          { key: 'password_entered', label: 'Password entered?', type: 'confirm' },
        ],
      },
      {
        id: 'click-login',
        title: 'Click Login',
        description: 'Submit login form.',
        type: 'manual',
        instructions: 'Click Login.',
        inputs: [
          { key: 'login_clicked', label: 'Login clicked?', type: 'confirm' },
        ],
      },
      {
        id: 'open-mail',
        title: 'Open Mail',
        description: 'Open target mail message.',
        type: 'manual',
        instructions: 'Open mail.',
        inputs: [
          { key: 'mail_opened', label: 'Mail opened?', type: 'confirm' },
        ],
      },
      {
        id: 'read-code',
        title: 'Read Code',
        description: 'Read verification code from mail body.',
        type: 'manual',
        instructions: 'Read code.',
        inputs: [
          { key: 'code_read', label: 'Code read?', type: 'text', placeholder: '000000' },
        ],
      },
    ],
  },
]

// ─── localStorage ─────────────────────────────────────────────────────────────

interface BotProgress {
  pipelineId: string
  currentStep: number
  completedSteps: number[]
  manualInputs: Record<number, Record<string, string>>
  error?: {
    stepIndex: number
    stepId: string
    message: string
    timestamp: number
  }
}

type ProgressMap = Record<string, BotProgress>

function loadProgress(): ProgressMap {
  try { return JSON.parse(localStorage.getItem('pipeline_progress_v2') ?? '{}') } catch { return {} }
}


function uid() {
  return Math.random().toString(36).slice(2, 10)
}

function makePassword() {
  return `${Math.random().toString(36).slice(2, 8)}${Math.floor(1000 + Math.random() * 9000)}!`
}

function normalizeProviderName(name: string) {
  return name.trim().toLowerCase()
}

function resolveEmailPipeline(
  providers: EmailProviderDef[],
  selectedProviderId: string,
  pipelineType: 'creation' | 'trust',
) {
  const provider = providers.find(p => p.id === selectedProviderId)
  if (!provider) return null
  const providerName = normalizeProviderName(provider.name)
  return EMAIL_PIPELINES.find(
    p => p.platform === 'email' && p.pipelineType === pipelineType && p.emailProvider === providerName,
  ) ?? null
}

// ─── Manual panel ─────────────────────────────────────────────────────────────

function ManualPanel({
  step, stepIdx, inputs, onComplete, error, onRetry,
}: {
  step: PipelineStep
  stepIdx: number
  inputs: Record<string, string>
  onComplete: (inputs: Record<string, string>) => void
  error?: { message: string; timestamp: number }
  onRetry?: () => void
}) {
  const [vals, setVals] = useState<Record<string, string>>(inputs)
  const allFilled = (step.inputs ?? []).filter(i => i.type !== 'textarea').every(i => !!vals[i.key]?.trim())

  return (
    <div className={`mt-3 rounded-xl border p-4 space-y-3 ${
      error
        ? 'border-red-700/60 bg-red-900/10'
        : 'border-amber-700/60 bg-amber-900/10'
    }`}>
      <div className="flex items-center gap-2">
        <span className={error ? 'text-red-400 text-sm font-semibold' : 'text-amber-400 text-sm font-semibold'}>
          {error ? '❌ Step Failed' : '⚠ Manual action required'}
        </span>
      </div>
      {error && (
        <div className="rounded-lg border border-red-700/40 bg-red-900/20 p-3">
          <p className="text-sm text-red-300">{error.message}</p>
        </div>
      )}
      {step.instructions && (
        <p className="text-sm text-gray-300 leading-relaxed">{step.instructions}</p>
      )}
      {step.inputs && step.inputs.length > 0 && (
        <div className="space-y-2">
          {step.inputs.map(inp => (
            <div key={inp.key}>
              <label className="text-xs text-gray-500 block mb-0.5">{inp.label}</label>
              {inp.type === 'textarea' ? (
                <textarea
                  value={vals[inp.key] ?? ''}
                  onChange={e => setVals(v => ({ ...v, [inp.key]: e.target.value }))}
                  placeholder={inp.placeholder}
                  rows={2}
                  className="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500 resize-none"
                />
              ) : (
                <input
                  type={inp.type === 'confirm' ? 'text' : inp.type}
                  value={vals[inp.key] ?? ''}
                  onChange={e => setVals(v => ({ ...v, [inp.key]: e.target.value }))}
                  placeholder={inp.placeholder}
                  className="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              )}
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <Button onClick={() => onComplete(vals)} disabled={!allFilled} className="flex-1 justify-center">
          {error ? 'Retry Step' : 'Continue'} → Step {stepIdx + 2}
        </Button>
        {error && onRetry && (
          <Button onClick={onRetry} variant="outline" className="justify-center">
            Clear Error
          </Button>
        )}
      </div>
    </div>
  )
}

// ─── Email Pipeline view by Run ───────────────────────────────────────────────

function EmailPipelineViewByRun({
  pipeline, progress, setProgress, expandedRun, onExpandRun, onAdvanceRun, onRemoveRun,
}: {
  pipeline: Pipeline
  progress: ProgressMap
  setProgress: (p: ProgressMap | ((prev: ProgressMap) => ProgressMap)) => void
  expandedRun: string | null
  onExpandRun: (runId: string | null) => void
  onAdvanceRun: (runId: string, inputs: Record<string, string>) => void
  onRemoveRun: (runId: string) => void
}) {
  const assignedRuns = Object.entries(progress)
    .filter(([, p]) => p.pipelineId === pipeline.id)
    .map(([id]) => id)
  const unassignedRunIds = Array.from({ length: 10 }, (_, i) => `run-${i}`)
    .filter(id => !assignedRuns.includes(id))

  return (
    <div className="grid grid-cols-3 gap-4">
      {/* Run list */}
      <div className="col-span-1 space-y-2">
        <p className="text-xs text-gray-500 uppercase tracking-wider px-1 mb-3">Runs on pipeline</p>
        {assignedRuns.length === 0 ? (
          <p className="text-xs text-gray-700 text-center py-4 rounded-lg border border-gray-700/30 bg-gray-800/20">None assigned yet</p>
        ) : (
          assignedRuns.map(runId => {
            const p = progress[runId]!
            const isDone = p.currentStep >= pipeline.steps.length
            const taskName = pipeline.pipelineType === 'creation' 
              ? `Task ${assignedRuns.indexOf(runId) + 1}`
              : `Mail ${assignedRuns.indexOf(runId) + 1}`
            return (
              <button
                key={runId}
                onClick={() => onExpandRun(expandedRun === runId ? null : runId)}
                className={`w-full text-left rounded-lg border p-3 transition-all ${
                  expandedRun === runId
                    ? 'border-blue-700/50 bg-blue-900/20'
                    : 'border-gray-700/40 bg-gray-800/20 hover:border-gray-600/50'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-200">{taskName}</span>
                  <span className="text-xs text-gray-500">{isDone ? '✓' : '→'}</span>
                </div>
                <div className="w-full h-1 rounded-full bg-gray-700 mb-1.5">
                  <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${Math.round((p.completedSteps.length / pipeline.steps.length) * 100)}%` }} />
                </div>
                <div className="text-xs text-gray-600">
                  {isDone ? 'Complete' : `Step ${p.currentStep + 1}/${pipeline.steps.length}`}
                </div>
              </button>
            )
          })
        )}

        {unassignedRunIds.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-700/30">
            <p className="text-xs text-gray-600 mb-2">Add run</p>
            <select
              defaultValue=""
              onChange={e => { if (e.target.value) { const id = e.target.value; setProgress(prev => ({ ...prev, [id]: { pipelineId: pipeline.id, currentStep: 0, completedSteps: [], manualInputs: {} } })); onExpandRun(id); e.target.value = '' } }}
              className="w-full rounded-lg border border-gray-600 bg-gray-800 px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">Select...</option>
              {unassignedRunIds.map(id => {
                const taskName = pipeline.pipelineType === 'creation' ? `Task ${parseInt(id.split('-')[1]) + 1}` : `Mail ${parseInt(id.split('-')[1]) + 1}`
                return <option key={id} value={id}>{taskName}</option>
              })}
            </select>
          </div>
        )}
      </div>

      {/* Run detail */}
      <div className="col-span-2">
        {expandedRun ? (
          (() => {
            const p = progress[expandedRun]!
            const isDone = p.currentStep >= pipeline.steps.length
            const runIndex = assignedRuns.indexOf(expandedRun)
            const taskName = pipeline.pipelineType === 'creation'
              ? `Task ${runIndex + 1}`
              : `Mail ${runIndex + 1}`

            return (
              <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-5 space-y-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-100">{taskName}</h3>
                    <p className="text-xs text-gray-600 mt-1">Progress: {p.completedSteps.length}/{pipeline.steps.length} steps completed</p>
                  </div>
                  <button
                    onClick={() => onRemoveRun(expandedRun)}
                    className="text-gray-600 hover:text-red-400 transition-colors text-sm"
                  >
                    Remove ✕
                  </button>
                </div>

                {/* Progress bar */}
                <div className="space-y-1">
                  <div className="w-full h-2 rounded-full bg-gray-700">
                    <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${Math.round((p.completedSteps.length / pipeline.steps.length) * 100)}%` }} />
                  </div>
                  <div className="text-xs text-gray-600 text-right">{Math.round((p.completedSteps.length / pipeline.steps.length) * 100)}%</div>
                </div>

                {/* Steps */}
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {pipeline.steps.map((step, idx) => {
                    const isCompleted = p.completedSteps.includes(idx)
                    const isCurrent = p.currentStep === idx
                    const isAuto = step.type === 'auto'

                    return (
                      <div
                        key={step.id}
                        className={`rounded-lg border p-3 transition-colors ${
                          isCompleted
                            ? 'border-emerald-700/40 bg-emerald-900/10'
                            : isCurrent
                              ? 'border-amber-700/60 bg-amber-900/10'
                              : 'border-gray-700/30 bg-gray-800/20'
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          <div className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border ${
                            isCompleted
                              ? 'bg-emerald-500/20 text-emerald-400 border-emerald-700/40'
                              : isCurrent
                                ? 'bg-amber-500/20 text-amber-400 border-amber-700/40'
                                : 'bg-gray-700/50 text-gray-600 border-gray-600/40'
                          }`}>
                            {isCompleted ? '✓' : idx + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`text-sm font-medium ${
                                isCompleted ? 'text-emerald-300' : isCurrent ? 'text-amber-300' : 'text-gray-300'
                              }`}>
                                {step.title}
                              </span>
                              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                                isAuto
                                  ? 'bg-blue-900/40 text-blue-400 border border-blue-700/40'
                                  : 'bg-amber-900/40 text-amber-400 border border-amber-700/40'
                              }`}>
                                {isAuto ? 'auto' : 'manual'}
                              </span>
                            </div>
                            <p className="text-xs text-gray-500 mt-1">{step.description}</p>

                            {/* Manual input for current step */}
                            {isCurrent && !isAuto && (
                              <ManualPanel
                                step={step}
                                stepIdx={idx}
                                inputs={p.manualInputs[idx] ?? {}}
                                onComplete={inputs => onAdvanceRun(expandedRun, inputs)}
                              />
                            )}

                            {/* Auto step button for current step */}
                            {isCurrent && isAuto && !isDone && (
                              <button
                                onClick={() => onAdvanceRun(expandedRun, {})}
                                className="mt-2 text-xs text-blue-400 hover:text-blue-300 border border-blue-700/40 bg-blue-900/20 rounded px-2 py-1 transition-colors"
                              >
                                ▶ Execute auto step
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {isDone && (
                  <div className="rounded-lg border border-emerald-700/40 bg-emerald-900/10 p-3">
                    <p className="text-sm text-emerald-300 font-semibold">✓ Pipeline Complete!</p>
                  </div>
                )}
              </div>
            )
          })()
        ) : (
          <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-5 text-center">
            <p className="text-gray-500 text-sm">Select a {pipeline.pipelineType === 'creation' ? 'task' : 'mail'} to see its progress</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Email Pipeline view ──────────────────────────────────────────────────────

function EmailPipelineView({
  pipeline, progress, onAddRun, onAdvanceRun, onRemoveRun, selectedProviderId,
}: {
  pipeline: Pipeline
  progress: ProgressMap
  onAddRun: (runId: string) => void
  onAdvanceRun: (runId: string, inputs: Record<string, string>) => void
  onRemoveRun: (runId: string) => void
  selectedProviderId: string
}) {
  const assignedRunIds = Object.entries(progress)
    .filter(([, p]) => p.pipelineId === pipeline.id)
    .map(([id]) => id)
  const unassignedRunIds = Array.from({ length: 10 }, (_, i) => `run-${i}`)
    .filter(id => !assignedRunIds.includes(id))

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 px-5 py-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-gray-100 text-base">{pipeline.title}</h3>
          <p className="text-sm text-gray-500 mt-0.5">{pipeline.description}</p>
          <div className="mt-2 text-xs text-gray-600">Provider-specific pipeline</div>
        </div>
        <div className="flex items-center gap-2 shrink-0 text-xs text-gray-600">
          <span>{pipeline.steps.length} steps</span>
          <span>·</span>
          <span>{assignedRunIds.length} {pipeline.pipelineType === 'creation' ? 'tasks' : 'mails'} running</span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4">
        {/* Steps */}
        <div className="col-span-3 space-y-2">
          {pipeline.steps.map((step, idx) => {
            const isAuto = step.type === 'auto'
            const runCount = assignedRunIds.filter(runId => {
              const p = progress[runId]
              return p && p.currentStep === idx && !p.completedSteps.includes(idx)
            }).length
            const anyWaiting = runCount > 0

            return (
              <div
                key={step.id}
                className={`rounded-xl border p-4 transition-colors ${
                  anyWaiting && !isAuto
                    ? 'border-amber-700/60 bg-amber-900/10'
                    : 'border-gray-700/50 bg-gray-800/30'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                    anyWaiting
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-700/50'
                      : 'bg-gray-700/50 text-gray-500 border border-gray-600/40'
                  }`}>
                    {idx + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-200 text-sm">{step.title}</span>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                        isAuto
                          ? 'bg-blue-900/40 text-blue-400 border border-blue-700/40'
                          : 'bg-amber-900/40 text-amber-400 border border-amber-700/40'
                      }`}>
                        {isAuto ? 'auto' : 'manual'}
                      </span>
                      {step.algorithmId && (
                        <span className="text-[10px] text-gray-600 font-mono">{step.algorithmId}</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{step.description}</p>

                    {!isAuto && assignedRunIds.map(runId => {
                      const p = progress[runId]
                      if (!p || p.currentStep !== idx || p.completedSteps.includes(idx)) return null
                      return (
                        <ManualPanel
                          key={runId}
                          step={step}
                          stepIdx={idx}
                          inputs={p.manualInputs[idx] ?? {}}
                          onComplete={inputs => onAdvanceRun(runId, inputs)}
                        />
                      )
                    })}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Run panel */}
        <div className="col-span-2">
          <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">
              {pipeline.pipelineType === 'creation' ? 'Tasks on pipeline' : 'Mails on pipeline'}
            </p>
            {assignedRunIds.length === 0 ? (
              <p className="text-xs text-gray-700 text-center py-4">None assigned yet</p>
            ) : (
              <div className="space-y-2">
                {assignedRunIds.map((runId, idx) => {
                  const p = progress[runId]!
                  const step = pipeline.steps[p.currentStep]
                  const isDone = p.currentStep >= pipeline.steps.length
                  const pct = Math.round(((isDone ? pipeline.steps.length : p.completedSteps.length) / pipeline.steps.length) * 100)
                  const taskName = pipeline.pipelineType === 'creation' ? `Task ${idx + 1}` : `Mail ${idx + 1}`
                  return (
                    <div key={runId} className="rounded-lg border border-gray-700/40 bg-gray-900/40 p-3">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm font-medium text-gray-200">{taskName}</span>
                        <button onClick={() => onRemoveRun(runId)} className="text-xs text-gray-600 hover:text-red-400 transition-colors">✕</button>
                      </div>
                      <div className="w-full h-1 rounded-full bg-gray-700 mb-1.5">
                        <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${pct}%` }} />
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-600">
                          {isDone ? <span className="text-emerald-400">Complete</span> : <>Step {p.currentStep + 1}: {step?.title}</>}
                        </span>
                        <span className="text-xs text-gray-600">{pct}%</span>
                      </div>
                      {!isDone && step?.type === 'auto' && (
                        <button
                          onClick={() => onAdvanceRun(runId, {})}
                          className="mt-2 w-full text-xs text-blue-400 hover:text-blue-300 border border-blue-700/40 bg-blue-900/20 rounded py-1 transition-colors"
                        >
                          ▶ Execute auto step
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {unassignedRunIds.length > 0 && (
              <div className="mt-3 pt-3 border-t border-gray-700/30">
                {pipeline.pipelineType === 'creation' ? (
                  <>
                    <p className="text-xs text-gray-600 mb-2">Run email creation pipeline</p>
                    <Button
                      className="w-full justify-center"
                      disabled={!selectedProviderId}
                      onClick={() => onAddRun(unassignedRunIds[0])}
                    >
                      Create Email
                    </Button>
                  </>
                ) : (
                  <>
                    <p className="text-xs text-gray-600 mb-2">Add mail</p>
                    <select
                      defaultValue=""
                      onChange={e => { if (e.target.value) { onAddRun(e.target.value); e.target.value = '' } }}
                      className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
                    >
                      <option value="">Select a mail...</option>
                      {unassignedRunIds.map((id, idx) => (
                        <option key={id} value={id}>{`Mail ${idx + 1}`}</option>
                      ))}
                    </select>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Pipeline view by Bot ─────────────────────────────────────────────────────

function PipelineViewByBot({
  pipeline, bots, progress, expandedBot, onExpandBot, onAdvanceBot, onRemoveBot,
}: {
  pipeline: Pipeline
  bots: Bot[]
  progress: ProgressMap
  expandedBot: string | null
  onExpandBot: (botId: string | null) => void
  onAdvanceBot: (botId: string, inputs: Record<string, string>) => void
  onRemoveBot: (botId: string) => void
}) {
  const assignedBots = bots.filter(b => progress[b.id]?.pipelineId === pipeline.id)
  const unassignedBots = bots.filter(b => !assignedBots.find(a => a.id === b.id))

  return (
    <div className="grid grid-cols-3 gap-4">
      {/* Bot list */}
      <div className="col-span-1 space-y-2">
        <p className="text-xs text-gray-500 uppercase tracking-wider px-1 mb-3">Bots on pipeline</p>
        {assignedBots.length === 0 ? (
          <p className="text-xs text-gray-700 text-center py-4 rounded-lg border border-gray-700/30 bg-gray-800/20">None assigned yet</p>
        ) : (
          assignedBots.map(b => {
            const p = progress[b.id]!
            const isDone = p.currentStep >= pipeline.steps.length
            return (
              <button
                key={b.id}
                onClick={() => onExpandBot(expandedBot === b.id ? null : b.id)}
                className={`w-full text-left rounded-lg border p-3 transition-all ${
                  expandedBot === b.id
                    ? 'border-blue-700/50 bg-blue-900/20'
                    : 'border-gray-700/40 bg-gray-800/20 hover:border-gray-600/50'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-200">{b.name}</span>
                  <span className="text-xs text-gray-500">{isDone ? '✓' : '→'}</span>
                </div>
                <div className="w-full h-1 rounded-full bg-gray-700 mb-1.5">
                  <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${Math.round((p.completedSteps.length / pipeline.steps.length) * 100)}%` }} />
                </div>
                <div className="text-xs text-gray-600">
                  {isDone ? 'Complete' : `Step ${p.currentStep + 1}/${pipeline.steps.length}`}
                </div>
              </button>
            )
          })
        )}
      </div>

      {/* Bot detail */}
      <div className="col-span-2">
        {expandedBot ? (
          (() => {
            const bot = bots.find(b => b.id === expandedBot)!
            const p = progress[expandedBot]!
            const isDone = p.currentStep >= pipeline.steps.length

            return (
              <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-5 space-y-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-100">{bot.name}</h3>
                    <p className="text-xs text-gray-600 mt-1">Progress: {p.completedSteps.length}/{pipeline.steps.length} steps completed</p>
                  </div>
                  <button
                    onClick={() => onRemoveBot(expandedBot)}
                    className="text-gray-600 hover:text-red-400 transition-colors text-sm"
                  >
                    Remove ✕
                  </button>
                </div>

                {/* Progress bar */}
                <div className="space-y-1">
                  <div className="w-full h-2 rounded-full bg-gray-700">
                    <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${Math.round((p.completedSteps.length / pipeline.steps.length) * 100)}%` }} />
                  </div>
                  <div className="text-xs text-gray-600 text-right">{Math.round((p.completedSteps.length / pipeline.steps.length) * 100)}%</div>
                </div>

                {/* Steps */}
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {pipeline.steps.map((step, idx) => {
                    const isCompleted = p.completedSteps.includes(idx)
                    const isCurrent = p.currentStep === idx
                    const isAuto = step.type === 'auto'

                    return (
                      <div
                        key={step.id}
                        className={`rounded-lg border p-3 transition-colors ${
                          isCompleted
                            ? 'border-emerald-700/40 bg-emerald-900/10'
                            : isCurrent
                              ? 'border-amber-700/60 bg-amber-900/10'
                              : 'border-gray-700/30 bg-gray-800/20'
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          <div className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border ${
                            isCompleted
                              ? 'bg-emerald-500/20 text-emerald-400 border-emerald-700/40'
                              : isCurrent
                                ? 'bg-amber-500/20 text-amber-400 border-amber-700/40'
                                : 'bg-gray-700/50 text-gray-600 border-gray-600/40'
                          }`}>
                            {isCompleted ? '✓' : idx + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`text-sm font-medium ${
                                isCompleted ? 'text-emerald-300' : isCurrent ? 'text-amber-300' : 'text-gray-300'
                              }`}>
                                {step.title}
                              </span>
                              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                                isAuto
                                  ? 'bg-blue-900/40 text-blue-400 border border-blue-700/40'
                                  : 'bg-amber-900/40 text-amber-400 border border-amber-700/40'
                              }`}>
                                {isAuto ? 'auto' : 'manual'}
                              </span>
                            </div>
                            <p className="text-xs text-gray-500 mt-1">{step.description}</p>

                            {/* Manual input for current step */}
                            {isCurrent && !isAuto && (
                              <ManualPanel
                                step={step}
                                stepIdx={idx}
                                inputs={p.manualInputs[idx] ?? {}}
                                onComplete={inputs => onAdvanceBot(expandedBot, inputs)}
                              />
                            )}

                            {/* Auto step button for current step */}
                            {isCurrent && isAuto && !isDone && (
                              <button
                                onClick={() => onAdvanceBot(expandedBot, {})}
                                className="mt-2 text-xs text-blue-400 hover:text-blue-300 border border-blue-700/40 bg-blue-900/20 rounded px-2 py-1 transition-colors"
                              >
                                ▶ Execute auto step
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {isDone && (
                  <div className="rounded-lg border border-emerald-700/40 bg-emerald-900/10 p-3">
                    <p className="text-sm text-emerald-300 font-semibold">✓ Pipeline Complete!</p>
                  </div>
                )}
              </div>
            )
          })()
        ) : (
          <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-5 text-center">
            <p className="text-gray-500 text-sm">Select a bot to see its progress</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Pipeline view ────────────────────────────────────────────────────────────

function PipelineView({
  pipeline, bots, progress, onAddBot, onAdvanceBot, onRemoveBot,
}: {
  pipeline: Pipeline
  bots: Bot[]
  progress: ProgressMap
  onAddBot: (botId: string) => void
  onAdvanceBot: (botId: string, inputs: Record<string, string>) => void
  onRemoveBot: (botId: string) => void
}) {
  const assignedBots   = bots.filter(b => progress[b.id]?.pipelineId === pipeline.id)
  const unassignedBots = bots.filter(b => !assignedBots.find(a => a.id === b.id))

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 px-5 py-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-gray-100 text-base">{pipeline.title}</h3>
          <p className="text-sm text-gray-500 mt-0.5">{pipeline.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0 text-xs text-gray-600">
          <span>{pipeline.steps.length} steps</span>
          <span>·</span>
          <span>{assignedBots.length} bots assigned</span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4">
        {/* Steps */}
        <div className="col-span-3 space-y-2">
          {pipeline.steps.map((step, idx) => {
            const isAuto = step.type === 'auto'
            const anyWaiting = assignedBots.some(b => {
              const p = progress[b.id]
              return p && p.currentStep === idx && !p.completedSteps.includes(idx)
            })

            return (
              <div
                key={step.id}
                className={`rounded-xl border p-4 transition-colors ${
                  anyWaiting && !isAuto
                    ? 'border-amber-700/60 bg-amber-900/10'
                    : 'border-gray-700/50 bg-gray-800/30'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                    anyWaiting
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-700/50'
                      : 'bg-gray-700/50 text-gray-500 border border-gray-600/40'
                  }`}>
                    {idx + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-200 text-sm">{step.title}</span>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                        isAuto
                          ? 'bg-blue-900/40 text-blue-400 border border-blue-700/40'
                          : 'bg-amber-900/40 text-amber-400 border border-amber-700/40'
                      }`}>
                        {isAuto ? 'auto' : 'manual'}
                      </span>
                      {step.algorithmId && (
                        <span className="text-[10px] text-gray-600 font-mono">{step.algorithmId}</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{step.description}</p>

                    {!isAuto && assignedBots.map(b => {
                      const p = progress[b.id]
                      if (!p || p.currentStep !== idx || p.completedSteps.includes(idx)) return null
                      return (
                        <ManualPanel
                          key={b.id}
                          step={step}
                          stepIdx={idx}
                          inputs={p.manualInputs[idx] ?? {}}
                          onComplete={inputs => onAdvanceBot(b.id, inputs)}
                        />
                      )
                    })}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Bot panel */}
        <div className="col-span-2">
          <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Bots on this pipeline</p>
            {assignedBots.length === 0 ? (
              <p className="text-xs text-gray-700 text-center py-4">None assigned yet</p>
            ) : (
              <div className="space-y-2">
                {assignedBots.map(b => {
                  const p = progress[b.id]!
                  const step = pipeline.steps[p.currentStep]
                  const isDone = p.currentStep >= pipeline.steps.length
                  const pct = Math.round(((isDone ? pipeline.steps.length : p.completedSteps.length) / pipeline.steps.length) * 100)
                  return (
                    <div key={b.id} className="rounded-lg border border-gray-700/40 bg-gray-900/40 p-3">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm font-medium text-gray-200">{b.name}</span>
                        <button onClick={() => onRemoveBot(b.id)} className="text-xs text-gray-600 hover:text-red-400 transition-colors">✕</button>
                      </div>
                      <div className="w-full h-1 rounded-full bg-gray-700 mb-1.5">
                        <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${pct}%` }} />
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-600">
                          {isDone ? <span className="text-emerald-400">Complete</span> : <>Step {p.currentStep + 1}: {step?.title}</>}
                        </span>
                        <span className="text-xs text-gray-600">{pct}%</span>
                      </div>
                      {!isDone && step?.type === 'auto' && (
                        <button
                          onClick={() => onAdvanceBot(b.id, {})}
                          className="mt-2 w-full text-xs text-blue-400 hover:text-blue-300 border border-blue-700/40 bg-blue-900/20 rounded py-1 transition-colors"
                        >
                          ▶ Execute auto step
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {unassignedBots.length > 0 && (
              <div className="mt-3 pt-3 border-t border-gray-700/30">
                <p className="text-xs text-gray-600 mb-2">Add bot to pipeline</p>
                <select
                  defaultValue=""
                  onChange={e => { if (e.target.value) { onAddBot(e.target.value); e.target.value = '' } }}
                  className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Select a bot…</option>
                  {unassignedBots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PipelinesPage() {
  const [pipelineType, setPipelineType] = useState<'creation' | 'trust'>('creation')
  const [section, setSection] = useState<'reddit' | 'email'>('reddit')
  const [redditView, setRedditView] = useState<'steps' | 'bots'>('steps')
  const [emailView, setEmailView] = useState<'steps' | 'runs'>('steps')
  const [emailPipelineType, setEmailPipelineType] = useState<'creation' | 'trust'>('creation')
  const [selectedEmailProviderId, setSelectedEmailProviderId] = useState<string>('')
  const [expandedBot, setExpandedBot] = useState<string | null>(null)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [progress, setProgress] = useState<ProgressMap>(loadProgress)

  const { data: bots = [] } = useQuery({ queryKey: ['bots'], queryFn: () => getBots() })
  const { data: emailProviders = [] } = useQuery({ queryKey: ['email-platforms'], queryFn: () => getEmailPlatforms() })

  useEffect(() => { saveProgress(progress) }, [progress])
  useEffect(() => {
    if (!selectedEmailProviderId && emailProviders.length > 0) {
      setSelectedEmailProviderId(emailProviders[0].id)
    }
  }, [emailProviders, selectedEmailProviderId])

  const redditPipeline = PIPELINES.find(p => p.platform === 'reddit' && p.pipelineType === pipelineType)!
  const emailPipeline = resolveEmailPipeline(emailProviders, selectedEmailProviderId, emailPipelineType)

  const pendingManual = Object.entries(progress).reduce((count, [, p]) => {
    const pl = PIPELINES.concat(EMAIL_PIPELINES).find(pipe => pipe.id === p.pipelineId)
    if (!pl) return count
    const step = pl.steps[p.currentStep]
    return step?.type === 'manual' && !p.completedSteps.includes(p.currentStep) ? count + 1 : count
  }, 0)

  const addBot = (botId: string) => {
    setProgress(prev => ({
      ...prev,
      [botId]: { pipelineId: redditPipeline.id, currentStep: 0, completedSteps: [], manualInputs: {} },
    }))
    void syncBotPipelineState(botId, true)
  }

  const addEmailRun = async (runId: string) => {
    if (!emailPipeline) return
    if (emailPipeline.pipelineType === 'creation') {
      const provider = emailProviders.find(p => p.id === selectedEmailProviderId)
      if (!provider) return
      const accountAddress = `${provider.name.toLowerCase().replace(/\s+/g, '.')}.${uid()}@${provider.domain || 'example.com'}`
      const accountPassword = makePassword()
      await createEmail({
        type: provider.type,
        provider_id: provider.id,
        address: accountAddress,
        password: accountPassword,
        used_by_bot_id: null,
        ever_blocked: false,
        blocked_on_platforms: [],
      })
      setProgress(prev => ({
        ...prev,
        [runId]: {
          pipelineId: emailPipeline.id,
          currentStep: 0,
          completedSteps: [],
          manualInputs: {
            0: { provider: provider.name },
            1: { creds_ready: 'yes', generated_email: accountAddress, generated_password: accountPassword },
            4: { stored: 'yes' },
          },
        },
      }))
      return
    }
    setProgress(prev => ({
      ...prev,
      [runId]: { pipelineId: emailPipeline.id, currentStep: 0, completedSteps: [], manualInputs: {} },
    }))
  }

  const advanceBot = (botId: string, inputs: Record<string, string>) => {
    const current = progress[botId]
    if (current) {
      const nextStep = current.currentStep + 1
      const pipeline = PIPELINES.find(p => p.id === current.pipelineId)
      const done = !!pipeline && nextStep >= pipeline.steps.length
      void syncBotPipelineState(botId, !done)
    }

    setProgress(prev => {
      const p = prev[botId]
      if (!p) return prev
      const newManualInputs = Object.keys(inputs).length > 0
        ? { ...p.manualInputs, [p.currentStep]: inputs }
        : p.manualInputs
      return {
        ...prev,
        [botId]: {
          ...p,
          currentStep: p.currentStep + 1,
          completedSteps: [...p.completedSteps, p.currentStep],
          manualInputs: newManualInputs,
        },
      }
    })
  }

  const advanceRun = (runId: string, inputs: Record<string, string>) => {
    setProgress(prev => {
      const p = prev[runId]
      if (!p) return prev
      const newManualInputs = Object.keys(inputs).length > 0
        ? { ...p.manualInputs, [p.currentStep]: inputs }
        : p.manualInputs
      return {
        ...prev,
        [runId]: {
          ...p,
          currentStep: p.currentStep + 1,
          completedSteps: [...p.completedSteps, p.currentStep],
          manualInputs: newManualInputs,
        },
      }
    })
  }

  const removeBot = (botId: string) => {
    void syncBotPipelineState(botId, false)
    setProgress(prev => { const next = { ...prev }; delete next[botId]; return next })
  }

  const removeRun = (runId: string) => {
    setProgress(prev => { const next = { ...prev }; delete next[runId]; return next })
  }

  return (
    <div className="space-y-5">
      {pendingManual > 0 && (
        <div className="rounded-xl border border-amber-700/60 bg-amber-900/10 px-5 py-3 flex items-center gap-3">
          <span className="text-amber-400 text-lg">⚠</span>
          <p className="text-sm text-amber-300">
            <span className="font-semibold">{pendingManual} manual step{pendingManual > 1 ? 's' : ''}</span>
            {' '}require your attention.
          </p>
        </div>
      )}

      {/* Section switcher */}
      <div className="flex gap-3">
        <button
          onClick={() => setSection('reddit')}
          className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
            section === 'reddit'
              ? 'border-blue-700/50 bg-blue-900/20 text-blue-400'
              : 'border-gray-700/50 bg-gray-800/40 text-gray-500 hover:text-gray-300'
          }`}
        >
          🤖 Reddit Pipelines
        </button>
        <button
          onClick={() => setSection('email')}
          className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
            section === 'email'
              ? 'border-amber-700/50 bg-amber-900/20 text-amber-400'
              : 'border-gray-700/50 bg-gray-800/40 text-gray-500 hover:text-gray-300'
          }`}
        >
          📧 Email Pipelines
        </button>
      </div>

      {section === 'reddit' ? (
        <>
          {/* Platform label */}
          <div className="flex items-center gap-3">
            <span className="text-lg">🤖</span>
            <h2 className="text-base font-semibold text-gray-100">Reddit</h2>
            <div className="flex-1 h-px bg-gray-700/50" />
          </div>
          {/* Pipeline type tabs */}
          <div className="flex gap-2 items-center">
            <div className="flex gap-2">
              {(['creation', 'trust'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setPipelineType(t)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                    pipelineType === t
                      ? t === 'creation'
                        ? 'border-blue-700/50 bg-blue-900/20 text-blue-400'
                        : 'border-purple-700/50 bg-purple-900/20 text-purple-400'
                      : 'border-gray-700/50 bg-gray-800/40 text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {t === 'creation' ? '🆕 Account Creation' : '📈 Trust Building'}
                </button>
              ))}
            </div>
            <div className="flex-1" />

            {/* View mode tabs */}
            <div className="flex gap-2">
              {(['steps', 'bots'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setRedditView(v)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    redditView === v
                      ? 'border-gray-600 bg-gray-700/50 text-gray-100'
                      : 'border-gray-700/50 bg-gray-800/40 text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {v === 'steps' ? '📋 By Steps' : '🤖 By Bots'}
                </button>
              ))}
            </div>
          </div>

          {redditView === 'steps' ? (
            <PipelineView
              pipeline={redditPipeline}
              bots={bots}
              progress={progress}
              onAddBot={addBot}
              onAdvanceBot={advanceBot}
              onRemoveBot={removeBot}
            />
          ) : (
            <PipelineViewByBot
              pipeline={redditPipeline}
              bots={bots}
              progress={progress}
              expandedBot={expandedBot}
              onExpandBot={setExpandedBot}
              onAdvanceBot={advanceBot}
              onRemoveBot={removeBot}
            />
          )}
        </>
      ) : (
        <>
          {/* Platform label */}
          <div className="flex items-center gap-3">
            <span className="text-lg">📧</span>
            <h2 className="text-base font-semibold text-gray-100">Email</h2>
            <div className="flex-1 h-px bg-gray-700/50" />
          </div>

          {/* Provider selector */}
          <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-4">
            <p className="text-xs text-gray-500 mb-2">Email provider</p>
            <select
              value={selectedEmailProviderId}
              onChange={e => setSelectedEmailProviderId(e.target.value)}
              className="w-full max-w-sm rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">Select provider�</option>
              {emailProviders.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          {/* Pipeline type tabs */}
          <div className="flex gap-2 items-center">
            <div className="flex gap-2">
              {(['creation', 'trust'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setEmailPipelineType(t)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                    emailPipelineType === t
                      ? t === 'creation'
                        ? 'border-blue-700/50 bg-blue-900/20 text-blue-400'
                        : 'border-emerald-700/50 bg-emerald-900/20 text-emerald-400'
                      : 'border-gray-700/50 bg-gray-800/40 text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {t === 'creation' ? '🆕 Account Creation' : '✓ Verification'}
                </button>
              ))}
            </div>

            <div className="flex-1" />

            {/* View mode tabs */}
            <div className="flex gap-2">
              {(['steps', 'runs'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setEmailView(v)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    emailView === v
                      ? 'border-gray-600 bg-gray-700/50 text-gray-100'
                      : 'border-gray-700/50 bg-gray-800/40 text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {v === 'steps' ? '📋 By Steps' : emailPipelineType === 'creation' ? '📦 By Tasks' : '📧 By Mails'}
                </button>
              ))}
            </div>
          </div>

          {emailPipeline ? (
            emailView === 'steps' ? (
              <EmailPipelineView
                pipeline={emailPipeline}
                progress={progress}
                onAddRun={addEmailRun}
                onAdvanceRun={advanceRun}
                onRemoveRun={removeRun}
                selectedProviderId={selectedEmailProviderId}
              />
            ) : (
              <EmailPipelineViewByRun
                pipeline={emailPipeline}
                progress={progress}
                setProgress={setProgress}
                expandedRun={expandedRun}
                onExpandRun={setExpandedRun}
                onAdvanceRun={advanceRun}
                onRemoveRun={removeRun}
              />
            )
          ) : (
            <div className="rounded-xl border border-dashed border-gray-700/50 py-16 text-center">
              <p className="text-sm text-gray-500">No {emailPipelineType === 'creation' ? 'creation' : 'verification'} pipeline defined for this provider.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}










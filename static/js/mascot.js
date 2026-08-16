document.addEventListener('DOMContentLoaded', () => {
    // ----- DOM Refs -----
    const container = document.getElementById('mascot-container');
    const bubble = document.getElementById('mascot-speech-bubble');
    const bubbleText = document.getElementById('mascot-text');
    const avatar = document.getElementById('mascot-avatar');
    const closeBtn = document.getElementById('mascot-close');
    const continueBtn = document.getElementById('mascot-continue-btn');

    if (!container || !bubble || !avatar || !bubbleText) return;

    const isAuthenticated = window.MASCOT_AUTH === true;

    // ----- What each part of the UI does, keyed by data-mascot-target ----
    // Hover help ONLY fires on elements carrying one of these keys as their
    // data-mascot-target attribute — nothing is auto-explained. Add a new
    // curated box here + the matching attribute on the element to cover it.
    const HELP_TEXTS = {
        'login-btn': "Click here to sign in with your username and password.",
        'google-signin-btn': "Sign in instantly using your Google account instead of a password.",
        'journal-input': "This is your Journal. Write a line or two about your day here — I read it and turn it into insights on your mood and patterns.",
        'journal-save-btn': "Click here to save today's journal entry once you've written something.",
        'side-dock-nav': "This is your quick-navigation dock — jump straight to any part of EvolveX from here.",
        'offer-countdown': "This counts down to when the current launch offer ends — the price or bonus changes once it hits zero.",
        'nav-profile-link': "This opens your Profile — your journal history, guilds, rewards and account settings all live there.",
        'profile-account-tab': "Shows and lets you edit your basic account details — username, name, and bio.",
        'profile-password-tab': "Change your account password here.",
        'profile-journal-tab': "This tab shows every journal entry you've saved, in one place.",
        'profile-guilds-tab': "Shows the guilds you're part of, once that feature unlocks for your account.",
        'profile-rewards-tab': "Shows rewards you've earned, once that feature unlocks for your account.",
        'profile-level-bar': "Your current level and XP progress toward the next one.",
        'profile-warrior-stats': "Your lifetime stats — total XP, Win/Survive/Lose days, tasks completed, and your current and best streaks.",
        'add-task-btn': "Add a new task here — give it a title, a priority, and a due date. Higher priority earns more XP when you complete it.",
        'date-nav-panel': "This is the date panel. Use the arrows to move a day at a time, or tap the date to jump straight to any day.",
        'date-picker-input': "Pick any date directly here to jump to that day's tasks.",
        'td-stat-tasks-done': "Shows how many of today's tasks you've finished out of the total you added.",
        'td-stat-completed': "Total number of tasks you've marked done today.",
        'td-stat-skipped': "Tasks you skipped today — each skip costs you XP, so use it sparingly.",
        'td-stat-xp': "Total XP you've earned from tasks today.",
        'td-progress-bar': "Your progress toward today's Win threshold — cross it and today counts as a Win day.",
        'td-filter-btn': "Filter the task list — narrow it down by status or priority.",
        'task-row-pending': "A task you haven't acted on yet. Use the buttons on the right to mark it done, skip it, or delete it.",
        'task-row-completed': "A completed task — shown struck-through and dimmed. You've already earned its XP; hit Undo if you completed it by mistake.",
        'task-row-skipped': "A skipped task — dimmed, and it cost you XP. Hit Undo to put it back to pending.",
        'task-complete-btn': "Marks this task as done and awards its XP immediately.",
        'task-skip-btn': "Skips this task for today — this costs you XP, so only skip what you really won't do.",
        'task-delete-btn': "Deletes this task permanently — this can't be undone.",
        'task-undo-btn': "Undoes this task's completed or skipped status and puts it back to pending.",
        'willpower-complete-btn': "Marks this willpower challenge as done — worth +7 XP.",
        'willpower-skip-btn': "Skips this willpower challenge — costs you −7 XP.",
        'willpower-delete-btn': "Deletes this willpower challenge permanently.",
        'willpower-undo-btn': "Undoes this challenge's completed or skipped status and puts it back to pending.",
        'wp-stat-xp': "Willpower XP you've earned (or lost) today from completing or skipping challenges.",
        'wp-stat-completed': "How many willpower challenges you've completed today.",
        'wp-stat-skipped': "How many willpower challenges you've skipped today — each one cost you XP.",
        'wp-stat-total': "Total willpower challenges you've added for today.",
        'wp-stat-streak': "How many days in a row you've kept up with your willpower challenges.",
        'wp-weekly-summary': "A day-by-day view of this week — filled dots mean you showed up that day.",
        'wp-streak-ring': "A visual ring showing your current willpower streak — the fuller the ring, the longer the streak.",
        'wp-week-xp': "Your net Willpower XP for this week — how much you earned from completions minus what you lost from skips.",
        'boss-stats-row': "Your boss-fight stats — win streak, bosses defeated, total victories, and win rate.",
        'boss-recent-battles': "Your most recent boss battles and the XP you earned defeating them.",
        'boss-journey-map': "The full path from Level 1 to Level 10 — each node is a boss standing between you and the next level.",
        'boss-challenge-btn': "Take on a Boss Fight here — it turns one of your goals into an RPG-style battle.",
        'diet-goal-cards': "Pick your physique goal here — I use it to build a personalized AI diet plan for you.",
        'diet-details-form': "Fill this in with your details — I use it to work out your daily calorie and macro targets.",
        'diet-personal-info': "Your gender, age, weight, height and activity level go here — these drive the calorie math.",
        'diet-custom-targets': "Set your own daily calorie and macro numbers here if you'd rather not use the AI-calculated ones.",
        'diet-generate-plan-btn': "Once your details are filled in, click here and I'll generate your AI diet plan.",
        'diet-macro-targets': "These are your daily targets — calories, protein, carbs and fat — based on your goal and details.",
        'diet-start-tracking-btn': "Click here to start tracking your diet plan from today.",
        'diet-date-nav': "Move between days here — arrows step one day at a time, or tap the date to jump anywhere.",
        'diet-date-picker': "Pick any date directly to jump straight to that day's meals.",
        'diet-cal-card': "Today's calories logged against your daily target, with your Win/Survive/Lose status for the day.",
        'diet-protein-card': "Today's protein intake against your daily target.",
        'diet-carbs-card': "Today's carb intake against your daily target.",
        'diet-fat-card': "Today's fat intake against your daily target.",
        'diet-photo-upload-zone': "Upload a photo of your meal here — I'll read it and estimate the macros automatically.",
        'diet-analyze-photo-btn': "Click here once your photo's uploaded — I'll analyze it and estimate the items and macros.",
        'diet-log-photo-btn': "Click here to save the meal from your photo, once you've reviewed the items.",
        'diet-food-search': "Search for a food or type its name — pick a match and I'll fill in its calories and macros for you.",
        'diet-log-food-btn': "Adds this meal to today's log using whatever's filled in above — the search result, AI estimate, or manual quantity.",
        'diet-edit-goals-link': "Update your calorie and macro targets here.",
        'diet-cheat-checkbox': "Tick this if it's a cheat meal — it's still logged, but costs a small point penalty.",
        'diet-meal-row': "A meal you've logged today — its calories and macros are shown here.",
        'diet-meal-cheat-btn': "Toggle whether this meal counts as a cheat meal.",
        'diet-meal-delete-btn': "Deletes this logged meal permanently.",
        'roadmap-goal-input': "Type the goal you want a roadmap for — the more specific, the better the plan I can build.",
        'roadmap-example-chips': "Tap any of these example goals to fill the goal field instantly.",
        'roadmap-generate-btn': "Once your goal and preferences are filled in, click here — I'll turn it into a personalized step-by-step roadmap.",
        'roadmap-clarify-submit': "Answer these to help me tailor the roadmap to exactly what you need, then submit to generate it.",
        'roadmap-mission-btn': "Start today's roadmap mission here — it breaks your bigger goal into a daily step.",
        'test-meta': "Shows how many marks the checkpoint test is worth in total, the passing mark, and how many questions there are.",
        'test-submit-btn': "Submits your answers for AI grading — make sure you've answered everything first.",
        'test-result-banner': "Shows whether you passed this checkpoint — green means you cleared it and unlocked the next phase, red means you need to retake it.",
        'test-retake-btn': "Restudy the material and take the checkpoint test again.",
        'rp-range-selector': "Switch how many days of history this page shows — 7, 30, or 90 days.",
        'rp-stat-total-xp': "Your all-time XP total across every part of EvolveX.",
        'rp-stat-task-xp': "XP earned from completing To-Do tasks in this period.",
        'rp-stat-willpower-xp': "XP earned from Willpower challenges in this period.",
        'rp-stat-diet-xp': "XP earned from logging meals in this period.",
        'rp-stat-roadmap-xp': "XP earned from Roadmap missions in this period.",
        'rp-stat-day-status': "Today's status — Win, Survive, or Lose — based on how many points you've earned so far today.",
        'rp-stat-win-days': "How many days in this period counted as a Win.",
        'rp-stat-avg-ring': "Your average XP earned per active day in this period.",
        'rp-chart-xp-trend': "Your cumulative XP over time, broken down by Task, Willpower, Diet and Roadmap XP.",
        'rp-chart-day-results': "How your days broke down — Win, Survive, or Lose — over this period.",
        'rp-chart-xp-distribution': "A radar view of where your XP is coming from and how consistent you've been.",
        'rp-chart-heatmap': "A day-by-day map of your activity — darker squares mean stronger days.",
        'rp-chart-xp-source': "What share of your XP came from Tasks, Willpower, Diet, and Roadmap.",
        'rp-chart-weekly-consistency': "How active you were each week — higher bars mean more days showed activity.",
        'rp-chart-streak-history': "Your daily streak over time, and your best streak in this period.",
        'rp-achievements': "Badges you've unlocked by hitting milestones — streaks, XP totals, and task counts.",
        'rp-insight-bar': "A quick takeaway based on your recent activity.",
        'analyzer-reanalyze-btn': "Click here to re-run the AI analysis with your latest activity — useful if you've logged something new since the last report.",
        'analyzer-type-tabs': "Switch between analysis types here — each one looks at your data from a different angle.",
        'analyzer-section-reports': "A breakdown of each area — Tasks, Willpower, Diet, Roadmap, Boss Fights — with its own score, grade, and what's working or not.",
        'analyzer-verdict': "My overall read on how you're doing right now, plus how confident I am in this analysis based on how much data you've given me.",
        'analyzer-evolution-score': "Your single overall score, 0–100, combining everything I track about you into one number and letter grade.",
        'analyzer-score-discipline': "How consistently you're showing up and following through — higher means fewer skipped days and tasks.",
        'analyzer-score-productivity': "How much you're actually getting done — task completion and output, not just showing up.",
        'analyzer-score-focus': "How concentrated your effort is on what matters most, versus spreading thin across everything.",
        'analyzer-score-evolution': "Your overall growth trend — whether you're improving, plateauing, or slipping compared to before.",
        'analyzer-hidden-patterns': "Patterns in your behavior you probably haven't noticed yourself — things I spotted by looking at your data over time.",
        'analyzer-success-patterns': "Habits and behaviors that are clearly working for you — keep doing these.",
        'analyzer-failure-patterns': "Recurring things that are holding you back — worth addressing directly.",
        'analyzer-opportunity-engine': "The highest-impact changes you could make right now, ranked by how much difference they'd likely make.",
        'analyzer-risk-burnout': "How likely you are to burn out soon, based on your recent pace and consistency.",
        'analyzer-risk-streak': "The chance you break your current streak in the next few days if nothing changes.",
        'analyzer-risk-goal': "The risk that you miss your current goal if your current pace continues.",
        'analyzer-risk-productivity': "The chance your output drops off in the near term based on recent trends.",
        'analyzer-risk-consistency': "How likely you are to become inconsistent — irregular activity — going forward.",
        'analyzer-goal-prediction': "Where I project you'll land — your odds of hitting your goal, expected level, days to next level-up, and expected XP.",
        'analyzer-trend-chart': "Your Evolution, Discipline, Productivity and Focus scores over time, so you can see whether you're trending up or down.",
        'analyzer-key-insights': "The most important individual observations from your data this period.",
        'analyzer-root-cause': "My best guess at why your patterns look the way they do — the underlying cause, not just the symptom.",
        'analyzer-recommendations': "Specific, actionable steps based on everything above — the concrete things to actually do next.",
        'analyzer-future-prediction': "A forward-looking read on where you're headed if you keep going the way you're going.",
        'premium-lock-card': "This feature is part of a paid plan — you'll need an active subscription to unlock it.",
        'premium-view-plans-btn': "Takes you to the pricing page where you can pick Monthly, 3-Month, or Lifetime.",
        'premium-back-link': "Go back to your Dashboard without upgrading.",
        'pricing-promo-banner': "A limited-time offer — buy before the date shown to get the bonus mentioned on the plan cards.",
        'pricing-active-sub': "Shows your current active plan and, if it's not lifetime, when it expires.",
        'pricing-plan-quarterly': "The 3-Month plan — everything in Monthly, plus advanced analytics, custom reminders, and AI recommendations.",
        'pricing-plan-yearly': "The Annual plan — EvolveX's most complete tier, with early feature access and priority support.",
        'pricing-plan-monthly': "The Monthly plan — full access to all features, billed month to month, cancel anytime.",
        'pricing-buy-quarterly': "Starts checkout for the 3-Month plan.",
        'pricing-buy-yearly': "Starts checkout for the Annual plan.",
        'pricing-buy-monthly': "Starts checkout for the Monthly plan.",
        'pricing-benefits': "A quick rundown of what Premium gets you across productivity, insights, security, and support.",
        'pricing-pay-razorpay': "Pay using Razorpay — supports cards and UPI.",
        'pricing-pay-paypal': "Pay using PayPal instead.",
    };
    const INTRO_TEXT = "👻 Hi, I'm Ghost! I'll guide you through EvolveX. If you ever need me, just click on me and I'll tell you all about this page. Happy journey, Evolver!";
    const HELP_MODE_ON_TEXT = "👻 I'm in guide mode now — hover over a highlighted box (press &amp; hold on mobile) and I'll explain it. Click me again to stop.";
    const HELP_MODE_WAITING_TEXT = "👻 Hover over any box and I'll explain it. Click me again to stop.";
    const HELP_MODE_WAITING_TEXT_TOUCH = "👻 Press and hold on any box and I'll explain it. Tap me again to stop.";

    let pendingTimer = null;
    function clearPendingTimer() {
        if (pendingTimer) {
            clearTimeout(pendingTimer);
            pendingTimer = null;
        }
    }

    // ----- Positioning -----
    function resetMascotPosition() {
        container.style.top = 'auto';
        container.style.left = 'auto';
        container.style.bottom = '2rem';
        container.style.right = '2rem';
    }

    let lastPositionedTarget = null;

    function moveMascotNearTarget(el) {
        lastPositionedTarget = el;
        const rect = el.getBoundingClientRect();
        const margin = 16;

        const isMobile = window.innerWidth <= 640;
        const containerW = isMobile ? 300 : 520;
        const containerH = isMobile ? 230 : 320;

        const spaceRight = window.innerWidth - rect.right;
        const spaceLeft = rect.left;
        const spaceBelow = window.innerHeight - rect.bottom;

        const fitsRight = spaceRight >= containerW + margin;
        const fitsLeft = spaceLeft >= containerW + margin;
        const fitsBelow = spaceBelow >= containerH + margin;

        let placement;
        if (fitsRight) placement = 'right';
        else if (fitsBelow) placement = 'below';
        else if (fitsLeft) placement = 'left';
        else placement = 'right';

        let left, top;
        if (placement === 'right') {
            left = rect.right + margin;
            top = rect.top + (rect.height / 2) - (containerH / 2);
        } else if (placement === 'left') {
            left = rect.left - containerW - margin;
            top = rect.top + (rect.height / 2) - (containerH / 2);
        } else {
            left = rect.left;
            top = rect.bottom + margin;
        }

        left = Math.max(margin, Math.min(left, window.innerWidth - containerW - margin));
        top = Math.max(margin, Math.min(top, window.innerHeight - containerH - margin));

        container.style.bottom = 'auto';
        container.style.right = 'auto';
        container.style.top = top + 'px';
        container.style.left = left + 'px';
    }

    let repositionRaf = null;
    let scrollSettleTimer = null;
    function scheduleReposition() {
        container.style.transition = 'none';
        clearTimeout(scrollSettleTimer);
        scrollSettleTimer = setTimeout(() => { container.style.transition = ''; }, 150);

        if (repositionRaf) return;
        repositionRaf = requestAnimationFrame(() => {
            repositionRaf = null;
            if (lastPositionedTarget && document.body.contains(lastPositionedTarget)) {
                moveMascotNearTarget(lastPositionedTarget);
            }
        });
    }
    window.addEventListener('resize', scheduleReposition);
    window.addEventListener('scroll', scheduleReposition, true);

    function clearHighlight() {
        document.querySelectorAll('.mascot-highlight').forEach(el => el.classList.remove('mascot-highlight'));
    }

    let typingToken = 0;
    function typeText(text, element, speed = 20) {
        const myToken = ++typingToken;
        element.innerHTML = '';
        let i = 0;
        function typeWriter() {
            if (myToken !== typingToken) return;
            if (i >= text.length) return;
            if (text[i] === '<') {
                const close = text.indexOf('>', i);
                if (close !== -1) {
                    element.innerHTML += text.slice(i, close + 1);
                    i = close + 1;
                    typeWriter();
                    return;
                }
            }
            element.innerHTML += text.charAt(i);
            i++;
            setTimeout(typeWriter, speed);
        }
        typeWriter();
    }
    function showBubble(text, showContinue) {
        bubble.classList.add('active');
        typeText(text, bubbleText);
        if (continueBtn) continueBtn.style.display = showContinue ? 'flex' : 'none';
    }
    function hideBubble() {
        typingToken++;
        bubble.classList.remove('active');
        bubbleText.innerHTML = '';
        if (continueBtn) continueBtn.style.display = 'none';
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && bubble.classList.contains('active')) handleClose();
    });

    // ===================================================================
    // Help mode: click the mascot to toggle it on/off. While on, hovering
    // (desktop) or press-and-holding (mobile) an element that carries a
    // data-mascot-target attribute shows its curated explanation. Anything
    // NOT explicitly tagged is ignored entirely — no auto-generated guesses,
    // no describing random page furniture. Only the small, curated boxes
    // (a stat card, a specific button, a form section, etc.) light up.
    // ===================================================================
    function resolveHoverTarget(raw) {
        if (!raw || (raw.closest && raw.closest('#mascot-container'))) return null;
        return raw.closest ? raw.closest('[data-mascot-target]') : null;
    }

    let helpModeActive = false;
    let hoverActiveEl = null;
    const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

    function activateHelpMode() {
        helpModeActive = true;
        hoverActiveEl = null;
        clearHighlight();
        resetMascotPosition();
        showBubble(HELP_MODE_ON_TEXT, true);
    }
    function deactivateHelpMode() {
        helpModeActive = false;
        hoverActiveEl = null;
        clearPendingTimer();
        clearHighlight();
        hideBubble();
        resetMascotPosition();
        lastPositionedTarget = null;
    }
    function showHelpFor(el) {
        const key = el.getAttribute('data-mascot-target');
        const text = HELP_TEXTS[key];
        if (!text) return; // tagged with an unknown key — nothing to say, stay silent
        hoverActiveEl = el;
        clearHighlight();
        document.querySelectorAll(`[data-mascot-target="${key}"]`).forEach(node => node.classList.add('mascot-highlight'));
        moveMascotNearTarget(el);
        showBubble(text, false);
    }
    function clearHelpFocus() {
        hoverActiveEl = null;
        clearHighlight();
        resetMascotPosition();
        lastPositionedTarget = null;
        showBubble(isTouchDevice ? HELP_MODE_WAITING_TEXT_TOUCH : HELP_MODE_WAITING_TEXT, false);
    }

    let hoverDebounce = null;
    document.addEventListener('mouseover', (e) => {
        if (!helpModeActive) return;
        const el = resolveHoverTarget(e.target);
        if (!el || el === hoverActiveEl) return;
        clearTimeout(hoverDebounce);
        hoverDebounce = setTimeout(() => showHelpFor(el), 60);
    });
    document.addEventListener('mouseout', (e) => {
        if (!helpModeActive || !hoverActiveEl) return;
        clearTimeout(hoverDebounce);
        const goingTo = e.relatedTarget ? resolveHoverTarget(e.relatedTarget) : null;
        if (goingTo === hoverActiveEl) return;
        clearHelpFocus();
    });

    let longPressTimer = null;
    let longPressEngaged = false;
    document.addEventListener('touchstart', (e) => {
        if (!helpModeActive) return;
        const el = resolveHoverTarget(e.target);
        if (!el) return;
        longPressEngaged = false;
        clearTimeout(longPressTimer);
        longPressTimer = setTimeout(() => {
            longPressEngaged = true;
            showHelpFor(el);
        }, 450);
    }, { passive: true });
    document.addEventListener('touchmove', () => clearTimeout(longPressTimer), { passive: true });
    document.addEventListener('touchend', (e) => {
        clearTimeout(longPressTimer);
        if (longPressEngaged) {
            // Swallow the tap so it doesn't also trigger the element's own
            // action (e.g. submitting a form). The bubble stays open until
            // the person taps the mascot or the close button.
            e.preventDefault();
        }
        longPressEngaged = false;
    }, { passive: false });

    function handleClose() {
        if (helpModeActive) { deactivateHelpMode(); return; }
        hideBubble();
        resetMascotPosition();
    }
    if (closeBtn) {
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            handleClose();
        });
    }
    if (continueBtn) {
        continueBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            hideBubble();
        });
    }
    avatar.addEventListener('click', (e) => {
        e.stopPropagation();
        if (helpModeActive) deactivateHelpMode();
        else activateHelpMode();
    });

    if (!isAuthenticated) {
        pendingTimer = setTimeout(() => {
            resetMascotPosition();
            showBubble(INTRO_TEXT, true);
        }, 1200);
    }
});
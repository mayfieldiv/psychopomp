# Product and feature showcases

## Footage

- Show the real product, filled with synthetic data from a local demo stack; the layer names the stack. Production and customer data stay out.
- Use the newest UI and brand, beta screens included, and show each screen whole: zoomed or cropped captures read as "too cropped".
- Play screens in real time, every device the story shows recorded in one take, so their clocks agree and each cause and its effect read as one. Cut only where nothing moves; a jump cut or a speed-up reads as an edit, and viewers ask whether the product is that fast. Acts played a little faster than life (1.35× read as natural) suit a montage that compresses a long wait; the brief says when a film uses them.
- Film a state the way a user sees it. An offline story is filmed offline, so the operating system shows it too; a test flag that fakes it for the app alone showed screens a real offline machine does not.
- Simulator footage: the iOS simulator recording shows the home screen, a black app-switch frame, and a white Safari frame before the page. Keep them in real time; they make the page open read as real. It writes a frame only on a change and ends on the last one, so hold that frame until the recording stopped, or two clocks on screen disagree.
- Browser footage: screenshot the page at device pixels about 30 times a second while a script drives it with a hand's mouse moves; Chromium's screencast sends CSS pixels (half a 2× page's), and Playwright's `recordVideo` kept about 2 s of a multi-second session. A 1440×900 detail page fills a 1280×800 Stage element.
- Terminal footage: typeset the session as its own terminal pass (a plan the film writes), render it into `assets/` first, and play it as footage beside the rest.
- A take script checks its own story: each device shows the same request, what one device shows is what the next receives, and the outcome the story ends on happened. It fails rather than keep footage that tells another story.

## Story

- Keep cause and effect in one view: the terminal sat left and the phone right, and each request and approval crossed between them.
- Make the feature's main selling point the spine of the story. Leave out what the product lacks rather than pitching an absence as a benefit, and keep version labels like "v1" out.
- Say exactly what is new. "Now, even offline" implied the whole product needed a connection, when only one flow had.
- Every claim, spoken, on screen, or implied by the pictures, traces to code, a test, or a run. A comparison with other products traces to a source the requester names and approves. A claim without evidence is cut, not softened.
- Use cases are situations the audience has lived, true to the feature's preconditions. For a phone approving an offline laptop: a broken network driver or VPN client (the phone has signal, the laptop has none), not a flight or hotel Wi-Fi.
- End on a climax. A logo that draws itself (an outline traced by a hot tip, then the letters springing in) landed well. Big announcement cards over a blurred frame read as filler; a short spoken line over the product did not.

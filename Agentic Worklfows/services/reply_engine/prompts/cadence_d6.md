<!-- Cadence day 6: calendar-hold touch. The hold needs Lorenzo's one-tap OK (Touch.requires_approval=True) and, in live, the CADENCE_D6_HOLD opt-in; this body goes out only once the hold actually exists on the Discovery Call calendar. It never claims the hold is "marked free" (GHL appointments have no transparency flag) and it never says an invite was sent: _create_hold writes the appointment with toNotify=False on purpose, because the prospect never agreed to this time, so GHL emails them nothing. Placeholders: {first_name} {slot1} {slot2} {booking_url} -->
Hey {first_name},

I put a 15-minute hold on my calendar for {slot1}. If {slot2} is better, say the word and I will move it.

Or grab any time here: {booking_url}

Lorenzo

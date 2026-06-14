document.addEventListener('DOMContentLoaded', async () => {
  async function loadInclude(selector, file) {
    const el = document.querySelector(selector);
    if (!el) return;

    try {
      const response = await fetch(file, { cache: 'no-cache' });
      if (!response.ok) {
        throw new Error(`No se pudo cargar ${file}`);
      }
      el.innerHTML = await response.text();
    } catch (error) {
      console.error(error);
    }
  }

  await loadInclude('#site-header', '/assets/includes/header.html');
  await loadInclude('#site-footer', '/assets/includes/footer.html');

  initReveal();
  initStickyHeader();
  initDropdown();
  initHeroScramble();
  initCurrentYear();
  initOpenStatus();
});

function initReveal() {
  const revealItems = document.querySelectorAll('.reveal');

  if (!revealItems.length) return;

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('show');
          obs.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.12
    });

    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add('show'));
  }
}

function initDropdown() {
  const dropdown = document.querySelector('.dropdown');
  const toggle = document.querySelector('.dropdown-toggle');

  if (!dropdown || !toggle) return;

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = dropdown.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });

  document.addEventListener('click', (e) => {
    if (!dropdown.contains(e.target)) {
      dropdown.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      dropdown.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    }
  });
}

function initStickyHeader() {
  const topbar = document.querySelector('.topbar');

  if (!topbar) return;

  const syncOffset = () => {
    document.documentElement.style.setProperty('--header-offset', `${topbar.offsetHeight + 12}px`);
  };

  const applyState = () => {
    topbar.classList.toggle('is-scrolled', window.scrollY > 18);
    syncOffset();
  };

  applyState();
  window.addEventListener('resize', syncOffset);
  window.addEventListener('scroll', applyState, { passive: true });
}

function initHeroScramble() {
  const el = document.querySelector('.hero-scramble');

  if (!el) return;

  const from = (el.dataset.textFrom || el.textContent || '').trim();
  const to = (el.dataset.textTo || el.textContent || '').trim();

  if (!from || !to || from === to) {
    el.textContent = to || from;
    return;
  }

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    el.textContent = to;
    return;
  }

  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const maxLength = Math.max(from.length, to.length);
  const target = to.padEnd(maxLength, ' ');
  const totalDuration = 5000;
  const holdDuration = 1400;
  const scrambleStart = holdDuration;
  const settleStart = 4100;
  const tickRate = 85;

  el.textContent = from;

  const startAt = performance.now();

  const tick = () => {
    const elapsed = performance.now() - startAt;

    if (elapsed < scrambleStart) {
      el.textContent = from;
      window.setTimeout(tick, tickRate);
      return;
    }

    if (elapsed >= totalDuration) {
      el.textContent = to;
      el.classList.remove('is-animating');
      return;
    }

    el.classList.add('is-animating');

    const revealProgress = Math.min(1, (elapsed - scrambleStart) / (settleStart - scrambleStart));
    let output = '';

    for (let i = 0; i < maxLength; i += 1) {
      const revealThreshold = revealProgress * maxLength;
      if (revealThreshold > i + Math.random() * 0.9) {
        output += target[i];
      } else {
        output += chars[Math.floor(Math.random() * chars.length)];
      }
    }

    if (elapsed > settleStart) {
      const settleProgress = (elapsed - settleStart) / (totalDuration - settleStart);
      const revealCount = Math.floor(settleProgress * maxLength);
      output = `${target.slice(0, revealCount)}${output.slice(revealCount)}`;
    }

    el.textContent = output.trimEnd();
    window.setTimeout(tick, tickRate);
  };

  window.setTimeout(tick, 700);
}

function initCurrentYear() {
  const yearEls = document.querySelectorAll('#current-year');
  if (!yearEls.length) return;

  const year = new Date().getFullYear();
  yearEls.forEach(el => {
    el.textContent = year;
  });
}

const HOLIDAY_CALENDARS = {
  2026: {
    euskadi: {
      '2026-01-01': 'Año Nuevo',
      '2026-01-06': 'Epifanía del Señor',
      '2026-03-19': 'San José',
      '2026-04-02': 'Jueves Santo',
      '2026-04-03': 'Viernes Santo',
      '2026-04-06': 'Lunes de Pascua',
      '2026-05-01': 'Fiesta del Trabajo',
      '2026-07-25': 'Santiago Apóstol',
      '2026-08-15': 'Asunción de la Virgen',
      '2026-10-12': 'Fiesta Nacional de España',
      '2026-12-08': 'Inmaculada Concepción',
      '2026-12-25': 'Navidad'
    },
    bizkaia: {
      '2026-07-31': 'San Ignacio de Loyola'
    },
    bilbao: {
      '2026-08-21': 'Viernes de la Semana Grande'
    },
    deusto: {
      // Cierre comercial adicional definido para el taller en Deusto.
      '2026-06-29': 'San Pedro de Deusto'
    }
  }
};

const DEFAULT_WEEK_SCHEDULE = {
  monday: { label: 'Lunes', closed: false, morning_open: '08:30', morning_close: '13:00', afternoon_open: '15:00', afternoon_close: '19:00' },
  tuesday: { label: 'Martes', closed: false, morning_open: '08:30', morning_close: '13:00', afternoon_open: '15:00', afternoon_close: '19:00' },
  wednesday: { label: 'Miércoles', closed: false, morning_open: '08:30', morning_close: '13:00', afternoon_open: '15:00', afternoon_close: '19:00' },
  thursday: { label: 'Jueves', closed: false, morning_open: '08:30', morning_close: '13:00', afternoon_open: '15:00', afternoon_close: '19:00' },
  friday: { label: 'Viernes', closed: false, morning_open: '08:30', morning_close: '15:00', afternoon_open: '', afternoon_close: '' },
  saturday: { label: 'Sábado', closed: true, morning_open: '', morning_close: '', afternoon_open: '', afternoon_close: '' },
  sunday: { label: 'Domingo', closed: true, morning_open: '', morning_close: '', afternoon_open: '', afternoon_close: '' }
};

function parseTimeString(value) {
  if (!value || !value.includes(':')) {
    return null;
  }

  const [hourText, minuteText] = value.split(':');
  const hour = Number.parseInt(hourText, 10);
  const minute = Number.parseInt(minuteText, 10);

  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return null;
  }

  return hour * 60 + minute;
}

function getMadridDateParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat('es-ES', {
    timeZone: 'Europe/Madrid',
    weekday: 'long',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(date);

  const values = {};
  parts.forEach((part) => {
    if (part.type !== 'literal') {
      values[part.type] = part.value;
    }
  });

  return {
    year: parseInt(values.year || '0', 10),
    month: parseInt(values.month || '0', 10),
    day: parseInt(values.day || '0', 10),
    hour: parseInt(values.hour || '0', 10),
    minute: parseInt(values.minute || '0', 10),
    weekday: (values.weekday || '').toLowerCase(),
    dateKey: `${values.year}-${values.month}-${values.day}`
  };
}

function getHolidayName(dateKey) {
  const year = Number.parseInt(dateKey.slice(0, 4), 10);
  const yearCalendar = HOLIDAY_CALENDARS[year];

  if (!yearCalendar) {
    return null;
  }

  return (
    yearCalendar.euskadi[dateKey] ||
    yearCalendar.bizkaia[dateKey] ||
    yearCalendar.bilbao[dateKey] ||
    yearCalendar.deusto[dateKey] ||
    null
  );
}

function getDayNumber(weekdayLabel) {
  const weekdayMap = {
    'lunes': 1,
    'martes': 2,
    'miércoles': 3,
    'jueves': 4,
    'viernes': 5,
    'sábado': 6,
    'domingo': 0
  };

  return weekdayMap[weekdayLabel] ?? -1;
}

function getScheduleForDay(dayNumber) {
  const scheduleSource = window.YBARRA_CONTACT?.schedule || DEFAULT_WEEK_SCHEDULE;
  const dayKeys = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
  const dayConfig = scheduleSource[dayKeys[dayNumber]];

  if (!dayConfig || dayConfig.closed) {
    return null;
  }

  const morningStart = parseTimeString(dayConfig.morning_open);
  const morningEnd = parseTimeString(dayConfig.morning_close);
  const afternoonStart = parseTimeString(dayConfig.afternoon_open);
  const afternoonEnd = parseTimeString(dayConfig.afternoon_close);

  if (morningStart === null || morningEnd === null) {
    return null;
  }

  const label = afternoonStart !== null && afternoonEnd !== null
    ? `${dayConfig.morning_open}–${dayConfig.morning_close} / ${dayConfig.afternoon_open}–${dayConfig.afternoon_close}`
    : `${dayConfig.morning_open}–${dayConfig.morning_close}`;

  return {
    label,
    morningStart,
    morningEnd,
    afternoonStart,
    afternoonEnd
  };
}

function getWeekdayLabelFromDate(date) {
  return new Intl.DateTimeFormat('es-ES', {
    timeZone: 'Europe/Madrid',
    weekday: 'long'
  }).format(date);
}

function getDateKeyFromDate(date) {
  const parts = new Intl.DateTimeFormat('es-ES', {
    timeZone: 'Europe/Madrid',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(date);

  const values = {};
  parts.forEach((part) => {
    if (part.type !== 'literal') {
      values[part.type] = part.value;
    }
  });

  return `${values.year}-${values.month}-${values.day}`;
}

function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

function renderStatusSubtext(content) {
  const statusSubtext = document.getElementById('open-status-subtext');

  if (!statusSubtext) {
    return;
  }

  statusSubtext.innerHTML = content;
}

function getScheduleMarkup(schedule) {
  if (!schedule) {
    return '';
  }

  if (schedule.afternoonStart === null) {
    return [
      '<span class="open-status-label">Horario de hoy</span>',
      `<span class="open-status-time">${schedule.label}</span>`
    ].join('');
  }

  const morningRange = `${String(Math.floor(schedule.morningStart / 60)).padStart(2, '0')}:${String(schedule.morningStart % 60).padStart(2, '0')}–${String(Math.floor(schedule.morningEnd / 60)).padStart(2, '0')}:${String(schedule.morningEnd % 60).padStart(2, '0')}`;
  const afternoonRange = `${String(Math.floor(schedule.afternoonStart / 60)).padStart(2, '0')}:${String(schedule.afternoonStart % 60).padStart(2, '0')}–${String(Math.floor(schedule.afternoonEnd / 60)).padStart(2, '0')}:${String(schedule.afternoonEnd % 60).padStart(2, '0')}`;

  return [
    '<span class="open-status-label">Horario de hoy</span>',
    `<span class="open-status-time">${morningRange} / ${afternoonRange}</span>`
  ].join('');
}

function getNextOpeningText(parts) {
  const currentDate = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12, 0, 0));

  for (let offset = 0; offset <= 14; offset += 1) {
    const candidate = new Date(currentDate);
    candidate.setUTCDate(candidate.getUTCDate() + offset);

    const dateKey = getDateKeyFromDate(candidate);
    const holidayName = getHolidayName(dateKey);
    const weekdayLabel = getWeekdayLabelFromDate(candidate).toLowerCase();
    const dayNumber = getDayNumber(weekdayLabel);
    const schedule = getScheduleForDay(dayNumber);

    if (!schedule || holidayName) {
      continue;
    }

    if (offset === 0) {
      return `Hoy abre a las ${schedule.label.split('–')[0]}`;
    }

    return `Vuelve a abrir el ${capitalize(weekdayLabel)} a las ${schedule.label.split('–')[0]}`;
  }

  return 'Consulta nuestro horario por teléfono o WhatsApp';
}

function initOpenStatus() {
  const statusBox = document.getElementById('open-status');
  const statusText = document.getElementById('open-status-text');
  const statusSubtext = document.getElementById('open-status-subtext');

  if (!statusBox || !statusText || !statusSubtext) return;

  const parts = getMadridDateParts();
  const dayNumber = getDayNumber(parts.weekday);
  const currentMinutes = parts.hour * 60 + parts.minute;
  const schedule = getScheduleForDay(dayNumber);
  const holidayName = getHolidayName(parts.dateKey);
  const isOpenMorning = schedule
    ? currentMinutes >= schedule.morningStart && currentMinutes < schedule.morningEnd
    : false;
  const isOpenAfternoon = schedule && schedule.afternoonStart !== null
    ? currentMinutes >= schedule.afternoonStart && currentMinutes < schedule.afternoonEnd
    : false;
  const isOpen = Boolean(schedule) && !holidayName && (isOpenMorning || isOpenAfternoon);

  if (isOpen) {
    statusBox.classList.add('open-status--open');
    statusBox.classList.remove('open-status--closed');
    statusText.textContent = 'Abierto ahora';
    renderStatusSubtext(getScheduleMarkup(schedule));
  } else {
    statusBox.classList.add('open-status--closed');
    statusBox.classList.remove('open-status--open');
    statusText.textContent = 'Cerrado ahora';

    if (holidayName) {
      renderStatusSubtext(`Hoy cerramos por festivo: ${holidayName}`);
    } else if (schedule && currentMinutes < schedule.morningStart) {
      renderStatusSubtext(getNextOpeningText(parts));
    } else if (schedule && schedule.afternoonStart !== null && currentMinutes >= schedule.morningEnd && currentMinutes < schedule.afternoonStart) {
      renderStatusSubtext(`Ahora está en pausa. Abre de nuevo a las ${String(Math.floor(schedule.afternoonStart / 60)).padStart(2, '0')}:${String(schedule.afternoonStart % 60).padStart(2, '0')}`);
    } else {
      renderStatusSubtext(getNextOpeningText({
        ...parts,
        hour: 23,
        minute: 59
      }));
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const heroCard = document.querySelector(".hero-media-card");
  const heroVideo = document.querySelector(".hero-media-video");

  if (!heroCard || !heroVideo) return;

  const showVideo = () => {
    heroCard.classList.add("is-video-ready");
  };

  if (heroVideo.readyState >= 3) {
    showVideo();
  } else {
    heroVideo.addEventListener("loadeddata", showVideo, { once: true });
    heroVideo.addEventListener("canplay", showVideo, { once: true });
  }
});

const slider = document.querySelector(".reviews-slider");

if (slider) {
  let scroll = 0;

  setInterval(() => {
    scroll += 1;
    slider.scrollLeft = scroll;

    if (scroll >= slider.scrollWidth / 2) {
      scroll = 0;
    }
  }, 20);
}

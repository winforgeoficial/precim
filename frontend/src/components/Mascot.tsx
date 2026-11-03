import type { Mascot as MascotData } from "../api";

type Props = { mood: MascotData["mood"]; size?: number };

/** Precinho, o cofrinho caçador. O humor muda conforme as ofertas. */
export default function Mascot({ mood, size = 120 }: Props) {
  const asleep = mood === "sleep";
  const party = mood === "party";
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" role="img"
         aria-label={asleep ? "Precinho dormindo" : party ? "Precinho comemorando" : "Precinho farejando"}
         className={party ? "animate-bob" : ""}>
      {/* orelhas */}
      <path d="M28 38 L22 14 L46 28 Z" fill="#e8738c" stroke="#3b2a2a" strokeWidth="3" strokeLinejoin="round" />
      <path d="M92 38 L98 14 L74 28 Z" fill="#e8738c" stroke="#3b2a2a" strokeWidth="3" strokeLinejoin="round" />
      {/* corpo */}
      <ellipse cx="60" cy="68" rx="44" ry="38" fill="#ff9db1" stroke="#3b2a2a" strokeWidth="3" />
      {/* fenda do cofrinho */}
      <rect x="44" y="34" width="32" height="6" rx="3" fill="#3b2a2a" />
      {party && (
        <g className="animate-sparkle">
          <circle cx="60" cy="18" r="9" fill="#ffc53d" stroke="#3b2a2a" strokeWidth="2.5" />
          <text x="60" y="22" textAnchor="middle" fontSize="11" fontWeight="700" fill="#3b2a2a">R$</text>
        </g>
      )}
      {/* olhos */}
      {asleep ? (
        <>
          <path d="M36 62 Q42 68 48 62" stroke="#3b2a2a" strokeWidth="3" fill="none" strokeLinecap="round" />
          <path d="M72 62 Q78 68 84 62" stroke="#3b2a2a" strokeWidth="3" fill="none" strokeLinecap="round" />
        </>
      ) : (
        <>
          <circle cx="42" cy="60" r="5" fill="#3b2a2a" />
          <circle cx="78" cy="60" r="5" fill="#3b2a2a" />
          <circle cx="44" cy="58" r="1.8" fill="#fff" />
          <circle cx="80" cy="58" r="1.8" fill="#fff" />
        </>
      )}
      {/* focinho */}
      <g className={mood === "sniff" ? "animate-sniff" : ""} style={{ transformOrigin: "60px 80px" }}>
        <ellipse cx="60" cy="80" rx="16" ry="12" fill="#ffc2cf" stroke="#3b2a2a" strokeWidth="3" />
        <circle cx="54" cy="80" r="2.6" fill="#3b2a2a" />
        <circle cx="66" cy="80" r="2.6" fill="#3b2a2a" />
      </g>
      {party && <path d="M46 94 Q60 104 74 94" stroke="#3b2a2a" strokeWidth="3" fill="none" strokeLinecap="round" />}
      {/* patinhas */}
      <rect x="32" y="100" width="12" height="12" rx="4" fill="#e8738c" stroke="#3b2a2a" strokeWidth="3" />
      <rect x="76" y="100" width="12" height="12" rx="4" fill="#e8738c" stroke="#3b2a2a" strokeWidth="3" />
      {asleep && (
        <g fontFamily="Fredoka" fontWeight="600" fill="#3b2a2a">
          <text x="94" y="30" fontSize="14" className="animate-zzz">z</text>
          <text x="102" y="20" fontSize="18" className="animate-zzz" style={{ animationDelay: ".8s" }}>Z</text>
        </g>
      )}
    </svg>
  );
}

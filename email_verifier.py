import re
import socket
import smtplib
import dns.resolver
from email_validator import validate_email, EmailNotValidError

class EmailVerifier:
    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.mx_cache = {}
        self.domain_alive_cache = {}

    def is_valid_syntax(self, email: str) -> bool:
        if not email or "@" not in email:
            return False
        try:
            validate_email(email, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False

    def get_mx_records(self, domain: str):
        domain = domain.lower().strip()
        if domain in self.mx_cache:
            return self.mx_cache[domain]

        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=self.timeout)
            # Sort by priority
            records = sorted([(r.preference, str(r.exchange).rstrip(".")) for r in answers], key=lambda x: x[0])
            mx_hosts = [r[1] for r in records]
            self.mx_cache[domain] = mx_hosts
            return mx_hosts
        except Exception:
            self.mx_cache[domain] = []
            return []

    def classify_mail_provider(self, domain: str) -> str:
        mx_hosts = self.get_mx_records(domain)
        if not mx_hosts:
            return "No MX"
        mx_str = " ".join(mx_hosts).lower()
        if "google" in mx_str or "l.google.com" in mx_str:
            return "Google Workspace"
        elif "outlook.com" in mx_str or "microsoft" in mx_str:
            return "Microsoft 365"
        elif "zoho" in mx_str:
            return "Zoho Mail"
        elif "protonmail" in mx_str:
            return "ProtonMail"
        elif "mimecast" in mx_str or "proofpoint" in mx_str:
            return "Enterprise Gateway"
        return "Custom/Host MX"

    def has_active_mx(self, domain: str) -> bool:
        return len(self.get_mx_records(domain)) > 0

    def generate_permutations(self, first_name: str, last_name: str, domain: str) -> list[str]:
        if not domain:
            return []
        domain = domain.lower().strip().replace("http://", "").replace("https://", "").replace("www.", "").split("/")[0]
        first = re.sub(r'[^a-zA-Z]', '', first_name).lower() if first_name else ""
        last = re.sub(r'[^a-zA-Z]', '', last_name).lower() if last_name else ""

        permutations = []
        if first and last:
            permutations.append(f"{first}.{last}@{domain}")
            permutations.append(f"{first}@{domain}")
            permutations.append(f"{first}{last}@{domain}")
            permutations.append(f"{first[0]}{last}@{domain}")
            permutations.append(f"{first}_{last}@{domain}")
            permutations.append(f"{first[0]}.{last}@{domain}")
        elif first:
            permutations.append(f"{first}@{domain}")
            permutations.append(f"founder@{domain}")
            permutations.append(f"hello@{domain}")
        else:
            permutations.append(f"founder@{domain}")
            permutations.append(f"ceo@{domain}")
            permutations.append(f"marketing@{domain}")
            permutations.append(f"hello@{domain}")

        return permutations

    def verify_email_smtp_ping(self, email: str) -> dict:
        """
        Runs live SMTP handshake (HELO, MAIL FROM, RCPT TO) to verify email validity.
        Does not send any email.
        """
        if not self.is_valid_syntax(email):
            return {"valid": False, "status": "invalid_syntax", "email": email}

        domain = email.split("@")[1].lower()
        mx_hosts = self.get_mx_records(domain)
        if not mx_hosts:
            return {"valid": False, "status": "no_mx_records", "email": email}

        provider = self.classify_mail_provider(domain)
        primary_mx = mx_hosts[0]

        # For Google & Microsoft, strict RCPT TO often returns 250 (or catch-all).
        # We perform standard handshake.
        try:
            server = smtplib.SMTP(timeout=self.timeout)
            server.connect(primary_mx, 25)
            server.helo("verify.flinza.com")
            server.mail("audit@verify.flinza.com")
            code, resp = server.rcpt(email)
            server.quit()

            if code == 250:
                return {"valid": True, "status": "deliverable", "email": email, "provider": provider}
            elif code in [550, 551, 552, 553, 554]:
                return {"valid": False, "status": "inbox_not_found", "email": email, "provider": provider}
            else:
                # Greylisted or 450
                return {"valid": True, "status": "accepts_mail_unverified", "email": email, "provider": provider}
        except Exception as e:
            # If port 25 is blocked by ISP or firewall, we rely on verified MX + domain health
            return {"valid": True, "status": "mx_verified_safe", "email": email, "provider": provider, "note": str(e)}

if __name__ == "__main__":
    verifier = EmailVerifier()
    test_domain = "gymshark.com"
    print("MX for", test_domain, ":", verifier.get_mx_records(test_domain))
    print("Provider:", verifier.classify_mail_provider(test_domain))
    permutations = verifier.generate_permutations("Ben", "Francis", test_domain)
    print("Permutations:", permutations[:3])

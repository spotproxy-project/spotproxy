# SpotProxy

SpotProxy is a cloud-native censorship resistance system that aims to minimize the cost of cloud-hosted proxies by co-opting cloud-native features for circumvention. 

Our current iteration of the project uses cost-effective and high-churn cloud instances to maximize the circumvention utility of cloud-hosted proxies. To achieve this, SpotProxy designs a circumvention infrastructure that constantly searches for cheaper VMs and refreshes the fleet for anti-blocking, with negligible downtime from the user's perspective. On this front, SpotProxy is currently compatible with Snowflake and Wireguard.

**We are actively developing the project. However, as of now, SpotProxy is not production-ready.** 

## 📰 News
- **[2024-12]**: Added support for [V2Ray](v2ray/README.md) (Prototype version available)!
- **[2024-08]**: We presented SpotProxy at USENIX Security 2024! Check out our [slides](https://www.usenix.org/conference/usenixsecurity24/presentation/kon) and [presentation video](https://www.youtube.com/watch?v=kx_wHENtCL8).
- **[2024-08]**: SpotProxy has been awarded the *Artifact Functional* and *Artifact Available* badges by USENIX Security 2024!
- **[2024-07]**: SpotProxy has been accepted to USENIX Security 2024! See you in Philadelphia!

## 🔥 Setup: 

1. Installation: [INSTALLATION.MD](https://github.com/spotproxy-project/spotproxy/blob/main/docs/INSTALLATION.md)
2. Controller setup: [controller_setup.md](https://github.com/spotproxy-project/spotproxy/blob/main/docs/controller_setup.md)
3. Instance manager setup: [instance_manager_setup.md](https://github.com/spotproxy-project/spotproxy/blob/main/docs/instance_manager_setup.md)
4. Client setup: [client_setup.md](https://github.com/spotproxy-project/spotproxy/blob/main/docs/client_setup.md)

## 🤝 Contributions

We are actively searching for collaborators to advance our mission of reducing cloud costs via co-opting cloud-native features for circumvention, of which SpotProxy is merely the first step. Please reach out to Patrick if you would like to contribute! We welcome and value all contributions to the project!

## 📚 More information

- [SpotProxy paper](https://www.cs-pk.com/sec24-spotproxy-final.pdf)
- [SpotProxy slides](https://www.usenix.org/conference/usenixsecurity24/presentation/kon)

## 📜 Citation

```bibtex
@inproceedings{kon2024spotproxy,
  title={SpotProxy: Rediscovering the Cloud for Censorship Circumvention},
  author={Kon, Patrick Tser Jern and Kamali, Sina and Pei, Jinyu and Barradas, Diogo and Chen, Ang and Sherr, Micah and Yung, Moti},
  booktitle={33rd USENIX Security Symposium (USENIX Security 24)},
  pages={2653--2670},
  year={2024}
}
```

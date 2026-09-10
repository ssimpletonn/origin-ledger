// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title PROVToken
/// @notice Utility-токен платформы OriginLedger.
///         Fixed supply (фиксированная эмиссия при деплое, дальнейший mint невозможен),
///         с поддержкой burn (сжигание) — используется контрактами LicenseMarket
///         и ContentRegistry для сжигания части комиссий/бондов.
contract PROVToken is ERC20, ERC20Burnable, Ownable {
    /// @param initialSupply Начальное количество токенов (в wei-эквиваленте, 18 decimals)
    /// @param treasury      Адрес, на который будет заминчен весь supply (казна проекта/DAO)
    constructor(uint256 initialSupply, address treasury)
        ERC20("OriginLedger Token", "PROV")
        Ownable(msg.sender)
    {
        require(treasury != address(0), "PROVToken: zero treasury");
        _mint(treasury, initialSupply);
    }

    /// @dev Явно не даём функции mint — эмиссия жёстко ограничена конструктором.
    ///      Это сознательное архитектурное решение для инновационно-экономической части:
    ///      supply не может быть увеличен ни владельцем, ни governance.

    /// @notice Разрешённые контракты платформы (LicenseMarket, ContentRegistry,
    ///         VerifierStaking) сжигают токены напрямую через burnFrom с allowance,
    ///         либо через отдельную привилегированную функцию burnFromPlatform,
    ///         чтобы не требовать от пользователя лишнего approve на каждый burn.
    mapping(address => bool) public isPlatformContract;

    event PlatformContractUpdated(address indexed account, bool allowed);

    function setPlatformContract(address account, bool allowed) external onlyOwner {
        isPlatformContract[account] = allowed;
        emit PlatformContractUpdated(account, allowed);
    }

    /// @notice Сжигание токенов со счёта пользователя платформенным контрактом
    ///         (LicenseMarket при комиссии, ContentRegistry при anti-spam bond и т.д.)
    /// @dev Требует, чтобы пользователь предварительно сделал approve на этот контракт
    ///      либо чтобы вызывающий сам являлся держателем токенов (после transferFrom).
    function burnFromPlatform(address account, uint256 amount) external {
        require(isPlatformContract[msg.sender], "PROVToken: caller is not platform");
        _burn(account, amount);
    }
}
